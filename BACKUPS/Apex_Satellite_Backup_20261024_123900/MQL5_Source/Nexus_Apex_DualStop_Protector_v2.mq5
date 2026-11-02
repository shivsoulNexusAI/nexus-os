//+------------------------------------------------------------------+
//|                        Nexus_Apex_DualStop_Protector_v2.mq5      |
//|        Multi-Asset Autonomous OCO & Dynamic Profit Ladder       |
//|               Compatible with: XAUUSD, BTCUSD, US30              |
//+------------------------------------------------------------------+
#property copyright "Nexus Institutional Quant"
#property link      "https://github.com/shivsoulNexusAI/Nexus-Apex-Dual-Stop-EA"
#property version   "2.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\OrderInfo.mqh>
#include <Trade\PositionInfo.mqh>

//--- Input Parameters
input group "=== Bracket Architecture ==="
input ulong   InpMagicNumber       = 888777;       // Unique Magic Identifier
input double  InpLotSize           = 0.02;         // Order Volume (e.g. 0.02)
input double  InpBracketCashGapUSD = 5.00;         // Cash Distance for Pending Stops ($)
input double  InpSmallCutUSD       = 0.60;         // Small Cut Hard Loss Ceiling ($)
input double  InpMaxSpreadUSD      = 2.50;         // Maximum Allowable Spread ($)
input int     InpMaxConsecutiveLoss= 3;            // Consecutive Loss Threshold
input int     InpCooldownSeconds   = 90;           // Cooldown Period (Seconds)

input group "=== Multi-Tier Profit Ladder ($ Realized) ==="
input double  InpTier1_TriggerUSD  = 1.00;         // Tier 1: Move to BE+ at $1.00
input double  InpTier2_TriggerUSD  = 2.00;         // Tier 2: Trigger $1.00 Lock at $2.00
input double  InpTier2_LockUSD     = 1.00;         // Tier 2: Guaranteed Realized Amount ($)
input double  InpTier3_TriggerUSD  = 5.00;         // Tier 3: Trigger $3.50 Lock at $5.00
input double  InpTier3_LockUSD     = 3.50;         // Tier 3: Guaranteed Realized Amount ($)
input double  InpTier4_TriggerUSD  = 10.00;        // Tier 4: Trigger $7.50 Lock at $10.00
input double  InpTier4_LockUSD     = 7.50;         // Tier 4: Guaranteed Realized Amount ($)
input double  InpTrailStepUSD      = 0.50;         // Cash Trail Step above Tier 4 ($)

//--- Objects & State Tracking
CTrade         m_trade;
COrderInfo     m_order;
CPositionInfo  m_position;

datetime g_lastLossTime      = 0;
int      g_consecutiveLosses = 0;
int      g_activeTier        = 0;
ulong    g_activeTicket      = 0;
double   g_highWaterProfit   = 0.0;

//+------------------------------------------------------------------+
//| Initialization                                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   m_trade.SetExpertMagicNumber(InpMagicNumber);
   m_trade.SetMarginMode();
   m_trade.SetTypeFillingBySymbol(_Symbol);

   PrintFormat("[NEXUS APEX v2] Initialized on %s | Contract: %0.2f | Digits: %d",
               _Symbol, SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE), _Digits);
   CheckAndDeployBracket();
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Deinitialization                                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Comment("");
}

//+------------------------------------------------------------------+
//| Price Delta from Desired Dollar Profit/Loss                      |
//+------------------------------------------------------------------+
double CashToPriceDistance(double cashAmount, double volume)
{
   double contractSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   if(contractSize <= 0.0 || volume <= 0.0) return 0.0;
   return cashAmount / (contractSize * volume);
}

//+------------------------------------------------------------------+
//| Main Execution Loop                                              |
//+------------------------------------------------------------------+
void OnTick()
{
   // 1. Anti-Chop Cooldown Check
   if(g_consecutiveLosses >= InpMaxConsecutiveLoss)
   {
      int elapsed = (int)(TimeCurrent() - g_lastLossTime);
      if(elapsed < InpCooldownSeconds)
      {
         Comment(StringFormat("🛡️ CHOP COOLDOWN: Resuming in %d sec...", InpCooldownSeconds - elapsed));
         return;
      }
      else
      {
         g_consecutiveLosses = 0;
         Comment("");
      }
   }

   // 2. Active Trade Management vs. Bracket Deployment
   int activeCount = CountActivePositions();

   if(activeCount > 0)
   {
      ManageProfitLadder();
   }
   else
   {
      g_activeTier      = 0;
      g_activeTicket    = 0;
      g_highWaterProfit = 0.0;
      CheckAndDeployBracket();
   }
}

//+------------------------------------------------------------------+
//| Active Position Counter                                          |
//+------------------------------------------------------------------+
int CountActivePositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Magic() == InpMagicNumber && m_position.Symbol() == _Symbol)
         {
            g_activeTicket = m_position.Ticket();
            count++;
         }
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| Deploy Synchronized Symmetrical Bracket                          |
//+------------------------------------------------------------------+
void CheckAndDeployBracket()
{
   int pendingBuy = 0, pendingSell = 0;

   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(m_order.SelectByIndex(i))
      {
         if(m_order.Magic() == InpMagicNumber && m_order.Symbol() == _Symbol)
         {
            if(m_order.OrderType() == ORDER_TYPE_BUY_STOP)  pendingBuy++;
            if(m_order.OrderType() == ORDER_TYPE_SELL_STOP) pendingSell++;
         }
      }
   }

   if(pendingBuy > 0 && pendingSell > 0) return;

   // Purge orphaned side
   PurgeAllPending();

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double spreadUSD = (ask - bid) * SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE) * InpLotSize;

   // Spread Guard
   if(spreadUSD > InpMaxSpreadUSD)
   {
      Comment(StringFormat("⚠️ SPREAD EXCEEDED ($%.2f > $%.2f). Pausing brackets.", spreadUSD, InpMaxSpreadUSD));
      return;
   }

   double priceGap = CashToPriceDistance(InpBracketCashGapUSD, InpLotSize);
   
   // Verify minimum broker Stop Level distance
   long stopLevelPoints = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double minAllowedDistance = stopLevelPoints * point;
   if(priceGap < minAllowedDistance)
   {
      priceGap = minAllowedDistance + (5 * point);
   }

   double buyPrice  = NormalizeDouble(ask + priceGap, _Digits);
   double sellPrice = NormalizeDouble(bid - priceGap, _Digits);

   m_trade.BuyStop(InpLotSize, buyPrice, _Symbol, 0, 0, ORDER_TIME_GTC, 0, "APEX_OCO_BUY");
   m_trade.SellStop(InpLotSize, sellPrice, _Symbol, 0, 0, ORDER_TIME_GTC, 0, "APEX_OCO_SELL");

   PrintFormat("[NEXUS APEX] Deployed Bracket on %s: BuyStop @ %f | SellStop @ %f | Gap: $%.2f",
               _Symbol, buyPrice, sellPrice, InpBracketCashGapUSD);
}

//+------------------------------------------------------------------+
//| Opposing Bracket Cancellation via Trade Transaction              |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest& request,
                        const MqlTradeResult& result)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      if(HistoryDealSelect(trans.deal))
      {
         if(HistoryDealGetInteger(trans.deal, DEAL_MAGIC) == InpMagicNumber)
         {
            long entry = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
            if(entry == DEAL_ENTRY_IN)
            {
               Print("[NEXUS APEX] Fill Confirmed. Purging opposing orders immediately...");
               PurgeAllPending();
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Purge Pending Orders                                             |
//+------------------------------------------------------------------+
void PurgeAllPending()
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(m_order.SelectByIndex(i))
      {
         if(m_order.Magic() == InpMagicNumber && m_order.Symbol() == _Symbol)
         {
            m_trade.OrderDelete(m_order.Ticket());
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Multi-Tier Profit Ladder & Small Cut Safeguard                   |
//+------------------------------------------------------------------+
void ManageProfitLadder()
{
   if(!m_position.SelectByTicket(g_activeTicket)) return;

   double profit       = m_position.Profit();
   double openPrice    = m_position.PriceOpen();
   double currentPrice = m_position.PriceCurrent();
   double slPrice      = m_position.StopLoss();
   double volume       = m_position.Volume();
   double point        = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   bool   isBuy        = (m_position.PositionType() == POSITION_TYPE_BUY);

   if(profit > g_highWaterProfit) g_highWaterProfit = profit;

   // 1. SMALL SL CUT: Instant termination if drawdown hits threshold
   if(profit <= -InpSmallCutUSD)
   {
      PrintFormat("[NEXUS APEX] Tight SL Executed: Profit = $%.2f. Closing ticket #%I64u.", profit, g_activeTicket);
      m_trade.PositionClose(g_activeTicket);
      g_consecutiveLosses++;
      g_lastLossTime = TimeCurrent();
      PurgeAllPending();
      CheckAndDeployBracket();
      return;
   }

   // 2. TIER 1: Move to Breakeven (+Spread Cushion) at $1.00 Gain
   if(profit >= InpTier1_TriggerUSD && g_activeTier < 1)
   {
      double beOffset = CashToPriceDistance(0.20, volume);
      double bePrice  = isBuy ? (openPrice + beOffset) : (openPrice - beOffset);
      bePrice         = NormalizeDouble(bePrice, _Digits);

      if(m_trade.PositionModify(g_activeTicket, bePrice, 0))
      {
         g_activeTier = 1;
         Print("[NEXUS APEX] 🛡️ Tier 1 Active: Position Immunized to BE+ Cushion.");
      }
   }

   // 3. TIER 2: Lock $1.00 Guaranteed Profit at $2.00 Gain
   if(profit >= InpTier2_TriggerUSD && g_activeTier < 2)
   {
      double lockDist  = CashToPriceDistance(InpTier2_LockUSD, volume);
      double lockPrice = isBuy ? (openPrice + lockDist) : (openPrice - lockDist);
      lockPrice        = NormalizeDouble(lockPrice, _Digits);

      if(m_trade.PositionModify(g_activeTicket, lockPrice, 0))
      {
         g_activeTier = 2;
         Print("[NEXUS APEX] 🚀 Tier 2 Active: $1.00 Guaranteed Profit Locked.");
      }
   }

   // 4. TIER 3: Lock $3.50 Guaranteed Profit at $5.00 Gain
   if(profit >= InpTier3_TriggerUSD && g_activeTier < 3)
   {
      double lockDist  = CashToPriceDistance(InpTier3_LockUSD, volume);
      double lockPrice = isBuy ? (openPrice + lockDist) : (openPrice - lockDist);
      lockPrice        = NormalizeDouble(lockPrice, _Digits);

      if(m_trade.PositionModify(g_activeTicket, lockPrice, 0))
      {
         g_activeTier = 3;
         Print("[NEXUS APEX] 💰 Tier 3 Active: $3.50 Guaranteed Profit Locked.");
      }
   }

   // 5. TIER 4: Lock $7.50 + Uncapped Dynamic Trailing at $10.00 Gain
   if(profit >= InpTier4_TriggerUSD)
   {
      if(g_activeTier < 4)
      {
         double lockDist  = CashToPriceDistance(InpTier4_LockUSD, volume);
         double lockPrice = isBuy ? (openPrice + lockDist) : (openPrice - lockDist);
         lockPrice        = NormalizeDouble(lockPrice, _Digits);

         if(m_trade.PositionModify(g_activeTicket, lockPrice, 0))
         {
            g_activeTier = 4;
            Print("[NEXUS APEX] 👑 Tier 4 Active: $7.50 Locked. Trailing Stop Initiated.");
         }
      }
      else
      {
         // Trail by (Trigger - Lock) Cash Distance
         double trailGapUSD = InpTier4_TriggerUSD - InpTier4_LockUSD;
         double trailDist   = CashToPriceDistance(trailGapUSD, volume);
         double stepDist    = CashToPriceDistance(InpTrailStepUSD, volume);

         if(isBuy)
         {
            double prospectiveSL = NormalizeDouble(currentPrice - trailDist, _Digits);
            if(prospectiveSL >= slPrice + stepDist)
            {
               m_trade.PositionModify(g_activeTicket, prospectiveSL, 0);
            }
         }
         else
         {
            double prospectiveSL = NormalizeDouble(currentPrice + trailDist, _Digits);
            if(slPrice == 0 || prospectiveSL <= slPrice - stepDist)
            {
               m_trade.PositionModify(g_activeTicket, prospectiveSL, 0);
            }
         }
      }
   }
}