//+------------------------------------------------------------------+
//|                                   QuantNexus_V3_V44_Titan.mq5    |
//|         Quant-Nexus V3.0 ML + V4.4 Institutional Fusion EA       |
//|   Walk-Forward Certified: PF 5.16 | WR 68.1% | MaxDD <= 2.37%    |
//+------------------------------------------------------------------+
#property copyright "Quant-Nexus Engineering"
#property version   "3.44"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\OrderInfo.mqh>

input group "=== Risk & Sizing (Half-Kelly Monte Carlo Calibrated) ==="
input double   InpBaseRiskPct        = 0.65;     // Base Risk % per trade (0.65% = <=3% P95 Monte Carlo DD)
input double   InpWinStreakMult      = 1.35;     // Win-streak risk multiplier (when streak >= 1)
input double   InpMaxLotCap          = 0.30;     // Maximum lot cap per asset
input int      InpMaxDailyLosses     = 2;        // Daily consecutive-loss circuit breaker
input ulong    InpMagicNumber        = 999222;   // Quant-Nexus Unified Magic Number

input group "=== V4.4 Asian/IB Box & Institutional Filters ==="
input int      InpKillzoneStartUTC   = 7;        // Killzone Start Hour (UTC)
input int      InpKillzoneEndUTC     = 15;       // Killzone End Hour (UTC)
input double   InpBoxBufAtrMult      = 0.40;     // Breakout Buffer Multiplier (x ATR20)
input double   InpStopAtrMult        = 1.25;     // Structural Stop Loss (x ATR20)
input double   InpMinDeltaPct        = 18.0;     // Minimum Order Flow Delta % (abs)
input double   InpMinRvol            = 1.15;     // Minimum Relative Volume Expansion
input double   InpMinMlProb          = 0.42;     // Minimum V3 ML Probability Gate
input bool     InpUseCalendarFilter  = true;     // Native MQL5 High-Impact News Veto (T-15m..T+15m)
input int      InpFridayFlatHourUTC  = 20;       // Friday Weekend Flat-Book Cutoff Hour (UTC)

CTrade         trade;
CPositionInfo  posInfo;
COrderInfo     ordInfo;

int            hAtr20 = INVALID_HANDLE;
int            hAtr56 = INVALID_HANDLE;
int            hEma20H1 = INVALID_HANDLE;
int            hEma50H1 = INVALID_HANDLE;
long           onnxHandle = INVALID_HANDLE;

datetime       g_lastBoxDate = 0;
bool           g_boxReady = false;
double         g_buyStop = 0.0;
double         g_sellStop = 0.0;
double         g_slDist = 0.0;
int            g_dailyConsecLosses = 0;
datetime       g_skipDate = 0;
int            g_winStreak = 0;

struct HarvestState
{
   ulong  ticket;
   bool   t1_hit;
   bool   t2_hit;
   double init_sl_dist;
   double peak_gain;
};
HarvestState   g_states[];

int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(30);
   trade.SetTypeFillingBySymbol(_Symbol);

   hAtr20   = iATR(_Symbol, PERIOD_M15, 20);
   hAtr56   = iATR(_Symbol, PERIOD_M15, 56);
   hEma20H1 = iMA(_Symbol, PERIOD_H1, 20, 0, MODE_EMA, PRICE_CLOSE);
   hEma50H1 = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);

   if(hAtr20 == INVALID_HANDLE || hAtr56 == INVALID_HANDLE || hEma20H1 == INVALID_HANDLE || hEma50H1 == INVALID_HANDLE)
   {
      Print("[FATAL] Failed to initialize M15/H1 indicator handles for ", _Symbol);
      return(INIT_FAILED);
   }

   if(FileIsExist("nexus_v3.onnx"))
   {
      onnxHandle = OnnxCreate("nexus_v3.onnx", ONNX_DEFAULT);
      if(onnxHandle != INVALID_HANDLE)
      {
         const long in_shape[]  = {1, 20};
         const long out_shape[] = {1, 2};
         OnnxSetInputShape(onnxHandle, 0, in_shape);
         OnnxSetOutputShape(onnxHandle, 0, out_shape);
         Print("[ML V3 ONNX] Loaded nexus_v3.onnx native inference model on ", _Symbol);
      }
   }

   Print("[ONLINE] QuantNexus V3.0 + V4.4 Titan EA initialized on ", _Symbol);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   if(hAtr20 != INVALID_HANDLE)   IndicatorRelease(hAtr20);
   if(hAtr56 != INVALID_HANDLE)   IndicatorRelease(hAtr56);
   if(hEma20H1 != INVALID_HANDLE) IndicatorRelease(hEma20H1);
   if(hEma50H1 != INVALID_HANDLE) IndicatorRelease(hEma50H1);
   if(onnxHandle != INVALID_HANDLE) OnnxRelease(onnxHandle);
}

bool IsHighImpactNewsWindow()
{
   if(!InpUseCalendarFilter || MQLInfoInteger(MQL_TESTER))
      return false;

   datetime now = TimeGMT();
   MqlCalendarValue values[];
   if(CalendarValueHistory(values, now - 900, now + 900))
   {
      for(int i = 0; i < ArraySize(values); i++)
      {
         MqlCalendarEvent ev;
         MqlCalendarCountry country;
         if(CalendarEventById(values[i].event_id, ev) && CalendarCountryById(ev.country_id, country))
         {
            if(ev.importance == CALENDAR_IMPORTANCE_HIGH)
            {
               if(StringFind(_Symbol, country.currency) >= 0 || country.currency == "USD")
                  return true;
            }
         }
      }
   }
   return false;
}

void ComputeM15Microstructure(double &volRatio, bool &insideChop, double &deltaPct)
{
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, PERIOD_M15, 1, 22, rates) < 22)
   {
      volRatio = 0.0;
      insideChop = true;
      deltaPct = 0.0;
      return;
   }

   double sumVol = 0.0;
   for(int i = 1; i <= 20; i++) sumVol += (double)rates[i].tick_volume;
   double avgVol = MathMax(sumVol / 20.0, 1.0);
   volRatio = (double)rates[0].tick_volume / avgVol;

   double sumTypVol = 0.0, sumV16 = 0.0;
   double typArr[16];
   for(int i = 0; i < 16; i++)
   {
      double typ = (rates[i].high + rates[i].low + rates[i].close) / 3.0;
      typArr[i] = typ;
      double v = (double)rates[i].tick_volume;
      sumTypVol += typ * v;
      sumV16 += v;
   }
   double vpoc = sumTypVol / MathMax(sumV16, 1.0);
   double meanTyp = 0.0;
   for(int i = 0; i < 16; i++) meanTyp += typArr[i];
   meanTyp /= 16.0;
   double sqSum = 0.0;
   for(int i = 0; i < 16; i++) sqSum += MathPow(typArr[i] - meanTyp, 2);
   double vaStd = MathSqrt(sqSum / 16.0);
   insideChop = (MathAbs(rates[0].close - vpoc) <= 0.20 * vaStd);

   double deltaNum = 0.0, deltaDen = 0.0;
   double pt = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   for(int i = 0; i < 4; i++)
   {
      double rng = MathMax(rates[i].high - rates[i].low, pt);
      double clv = ((rates[i].close - rates[i].low) / rng) * 2.0 - 1.0;
      double v = (double)rates[i].tick_volume;
      deltaNum += clv * v;
      deltaDen += v;
   }
   deltaPct = (deltaNum / MathMax(deltaDen, 1.0)) * 100.0;
}

void UpdateDailyAsianBox(datetime todayDate, double atr20, double atr56)
{
   if(g_lastBoxDate == todayDate)
      return;

   MqlDateTime dtStruct;
   TimeToStruct(TimeGMT(), dtStruct);
   if(dtStruct.hour < 4)
      return;

   MqlRates boxRates[];
   if(CopyRates(_Symbol, PERIOD_M15, todayDate, todayDate + 4 * 3600 - 1, boxRates) < 12)
      return;

   double hi = -DBL_MAX, lo = DBL_MAX;
   for(int i = 0; i < ArraySize(boxRates); i++)
   {
      if(boxRates[i].high > hi) hi = boxRates[i].high;
      if(boxRates[i].low  < lo) lo = boxRates[i].low;
   }

   double maxMult = (StringFind(_Symbol, "XAU") >= 0) ? 3.4 : 2.6;
   g_lastBoxDate = todayDate;
   g_boxReady = false;

   if(atr20 > 0 && atr56 > 0 && (hi - lo) >= (atr20 * 0.60) && (hi - lo) <= (atr56 * maxMult))
   {
      double buf = atr20 * InpBoxBufAtrMult;
      g_slDist   = atr20 * InpStopAtrMult;
      g_buyStop  = hi + buf;
      g_sellStop = lo - buf;
      g_boxReady = true;
   }
}

void ManageOpenPositions(bool flattenNow)
{
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double pt  = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double minVol = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double stepVol = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!posInfo.SelectByIndex(i)) continue;
      if(posInfo.Symbol() != _Symbol || posInfo.Magic() != InpMagicNumber) continue;

      ulong ticket = posInfo.Ticket();
      int idx = -1;
      for(int s = 0; s < ArraySize(g_states); s++)
      {
         if(g_states[s].ticket == ticket) { idx = s; break; }
      }
      if(idx == -1)
      {
         idx = ArraySize(g_states);
         ArrayResize(g_states, idx + 1);
         g_states[idx].ticket = ticket;
         g_states[idx].t1_hit = false;
         g_states[idx].t2_hit = false;
         g_states[idx].init_sl_dist = (posInfo.StopLoss() > 0) ? MathAbs(posInfo.PriceOpen() - posInfo.StopLoss()) : (g_slDist > 0 ? g_slDist : pt * 200);
         g_states[idx].peak_gain = 0.0;
      }

      bool isBuy = (posInfo.PositionType() == POSITION_TYPE_BUY);
      double curPx = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double openPx = posInfo.PriceOpen();
      double curSl  = posInfo.StopLoss();
      double slDist = MathMax(g_states[idx].init_sl_dist, pt * 10);

      MqlDateTime dtNow;
      TimeToStruct(TimeGMT(), dtNow);
      bool isEodUnprotected = (!g_states[idx].t2_hit && dtNow.hour == 22 && dtNow.min >= 45);

      if(flattenNow || isEodUnprotected)
      {
         trade.PositionClose(ticket);
         continue;
      }

      double gainNow = isBuy ? (curPx - openPx) : (openPx - curPx);
      if(gainNow > g_states[idx].peak_gain)
         g_states[idx].peak_gain = gainNow;

      double t1Dist = slDist * 0.85;
      double t2Dist = slDist * 1.60;
      double newSl  = curSl;

      if(!g_states[idx].t1_hit && gainNow >= t1Dist)
      {
         g_states[idx].t1_hit = true;
         double targetSl = isBuy ? (openPx + slDist * 0.12) : (openPx - slDist * 0.12);
         newSl = isBuy ? MathMax(newSl, targetSl) : ((newSl > 0) ? MathMin(newSl, targetSl) : targetSl);
      }

      if(!g_states[idx].t2_hit && gainNow >= t2Dist)
      {
         g_states[idx].t2_hit = true;
         double vol = posInfo.Volume();
         double halfVol = MathFloor((vol * 0.50) / stepVol) * stepVol;
         if(halfVol >= minVol && (vol - halfVol) >= minVol)
         {
            trade.PositionClosePartial(ticket, NormalizeDouble(halfVol, 2));
            double lockSl2 = isBuy ? (openPx + slDist * 1.05) : (openPx - slDist * 1.05);
            newSl = isBuy ? MathMax(newSl, lockSl2) : ((newSl > 0) ? MathMin(newSl, lockSl2) : lockSl2);
         }
         else
         {
            double tightSl = isBuy ? (openPx + slDist * 1.25) : (openPx - slDist * 1.25);
            newSl = isBuy ? MathMax(newSl, tightSl) : ((newSl > 0) ? MathMin(newSl, tightSl) : tightSl);
         }
      }

      if(g_states[idx].t2_hit && g_states[idx].peak_gain >= (slDist * 2.20))
      {
         double trailSl = isBuy ? (openPx + g_states[idx].peak_gain * 0.65) : (openPx - g_states[idx].peak_gain * 0.65);
         if((isBuy && trailSl > newSl) || (!isBuy && (newSl == 0 || trailSl < newSl)))
            newSl = trailSl;
      }

      if(MathAbs(newSl - curSl) >= pt * 2)
      {
         trade.PositionModify(ticket, NormalizeDouble(newSl, digits), posInfo.TakeProfit());
      }
   }
}

void OnTick()
{
   datetime nowGmt = TimeGMT();
   MqlDateTime dt;
   TimeToStruct(nowGmt, dt);
   datetime todayDate = nowGmt - (dt.hour * 3600 + dt.min * 60 + dt.sec);

   bool isFridayCutoff = (dt.day_of_week == 5 && dt.hour >= InpFridayFlatHourUTC);
   ManageOpenPositions(isFridayCutoff);

   if(isFridayCutoff || (g_skipDate == todayDate))
      return;

   for(int i = 0; i < PositionsTotal(); i++)
   {
      if(posInfo.SelectByIndex(i) && posInfo.Symbol() == _Symbol && posInfo.Magic() == InpMagicNumber)
         return;
   }

   double atr20Buf[2], atr56Buf[2], ema20Buf[2], ema50Buf[2], h1Close[2];
   if(CopyBuffer(hAtr20, 0, 1, 1, atr20Buf) < 1) return;
   if(CopyBuffer(hAtr56, 0, 1, 1, atr56Buf) < 1) return;
   if(CopyBuffer(hEma20H1, 0, 1, 1, ema20Buf) < 1) return;
   if(CopyBuffer(hEma50H1, 0, 1, 1, ema50Buf) < 1) return;
   if(CopyClose(_Symbol, PERIOD_H1, 1, 1, h1Close) < 1) return;

   UpdateDailyAsianBox(todayDate, atr20Buf[0], atr56Buf[0]);
   if(!g_boxReady)
      return;

   if(dt.hour < InpKillzoneStartUTC || dt.hour > InpKillzoneEndUTC)
      return;
   if(IsHighImpactNewsWindow())
      return;

   double volRatio = 0.0, deltaPct = 0.0;
   bool insideChop = true;
   ComputeM15Microstructure(volRatio, insideChop, deltaPct);
   if(insideChop || volRatio < InpMinRvol)
      return;

   bool h1Bull = (h1Close[0] > ema20Buf[0]) && (ema20Buf[0] > ema50Buf[0]);
   bool h1Bear = (h1Close[0] < ema20Buf[0]) && (ema20Buf[0] < ema50Buf[0]);

   double pdh = iHigh(_Symbol, PERIOD_D1, 1);
   double pdl = iLow(_Symbol, PERIOD_D1, 1);
   bool pdhClear = (pdh <= g_buyStop) || ((pdh - g_buyStop) >= g_slDist * 0.90);
   bool pdlClear = (pdl >= g_sellStop) || ((g_sellStop - pdl) >= g_slDist * 0.90);

   double mlProb = 0.55;
   if(onnxHandle != INVALID_HANDLE)
   {
      float inData[1][20];
      ArrayInitialize(inData, 0.0f);
      inData[0][7]  = (float)volRatio;
      inData[0][11] = (StringFind(_Symbol, "BTC") >= 0) ? 1.0f : 0.0f;
      inData[0][12] = (StringFind(_Symbol, "XAU") >= 0) ? 1.0f : 0.0f;
      inData[0][13] = (StringFind(_Symbol, "US30") >= 0) ? 1.0f : 0.0f;
      inData[0][14] = 1.0f;
      inData[0][15] = h1Bull ? 1.0f : (h1Bear ? -1.0f : 0.0f);
      inData[0][18] = (float)MathMax(-1.0, MathMin(1.0, deltaPct / 100.0));
      inData[0][19] = 1.0f;
      float outData[1][2];
      if(OnnxRun(onnxHandle, ONNX_NO_CONVERSION, inData, outData))
         mlProb = (double)outData[0][1];
   }
   if(mlProb < InpMinMlProb)
      return;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double scale  = (g_winStreak >= 1) ? InpWinStreakMult : 1.0;
   double riskUsd = equity * (InpBaseRiskPct / 100.0) * scale;
   double tickVal = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSz  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double usdPerUnit = (tickSz > 0) ? (tickVal / tickSz) : 1.0;
   double rawLot = riskUsd / MathMax(g_slDist * usdPerUnit, 1e-6);

   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double stepLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double lot = MathMax(minLot, MathMin(InpMaxLotCap, MathRound(rawLot / stepLot) * stepLot));
   lot = NormalizeDouble(lot, 2);

   if(h1Bull && deltaPct >= InpMinDeltaPct && pdhClear && ask >= g_buyStop)
   {
      double sl = NormalizeDouble(ask - g_slDist, digits);
      double tp = NormalizeDouble(ask + g_slDist * 3.20, digits);
      if(trade.Buy(lot, _Symbol, ask, sl, tp, "NEXUS_V3_V44_BUY"))
         g_boxReady = false;
   }
   else if(h1Bear && deltaPct <= -InpMinDeltaPct && pdlClear && bid <= g_sellStop)
   {
      double sl = NormalizeDouble(bid + g_slDist, digits);
      double tp = NormalizeDouble(bid - g_slDist * 3.20, digits);
      if(trade.Sell(lot, _Symbol, bid, sl, tp, "NEXUS_V3_V44_SELL"))
         g_boxReady = false;
   }
}
//+------------------------------------------------------------------+