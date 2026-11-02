//+------------------------------------------------------------------+
//|                                  Nexus_Apex_OCO_Protector.mq5   |
//|                        Autonomous Micro-Harvest & OCO Engine     |
//+------------------------------------------------------------------+
#property copyright "Nexus Omega Institutional"
#property link      "https://github.com/shivsoulNexusAI"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\OrderInfo.mqh>
#include <Trade\PositionInfo.mqh>

//--- Input Parameters
input group "=== Institutional Risk Settings ==="
input ulong  InpMagicNumber       = 999888;       // Unique Magic Identifier
input double InpLotSize           = 0.30;         // Bracket Order Volume
input double InpRiskDistancePoints= 200;          // SL Distance in Points
input double InpBufferPoints      = 15;           // Spread & Slippage Cushion

input group "=== Micro-Harvest Protection ==="
input double InpHarvestRatio      = 0.60;         // Volume to Close on Scalp (60%)
input double InpTargetHarvestR    = 0.50;         // Target Expansion to Harvest (+0.50R)
input int    InpTimerIntervalMs   = 250;          // Monitor Frequency (Milliseconds)

//--- Global Objects
CTrade         m_trade;
COrderInfo     m_order;
CPositionInfo  m_position;

//--- Internal State Tracking
ulong  g_buyStopTicket   = 0;
ulong  g_sellStopTicket  = 0;
bool   g_positionActive  = false;
bool   g_harvestExecuted = false;
ulong  g_activeTicket    = 0;

//+------------------------------------------------------------------+
//| Expert Initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   m_trade.SetExpertMagicNumber(InpMagicNumber);
   m_trade.SetMarginMode();
   m_trade.SetTypeFillingBySymbol(_Symbol);

   EventSetMillisecondTimer(InpTimerIntervalMs);
   Print("[NEXUS MQL5] Apex OCO Protector Initialized on ", _Symbol);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert Deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("[NEXUS MQL5] Apex OCO Protector Shutdown. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| Bracket Deployment Trigger                                       |
//+------------------------------------------------------------------+
void DeployBracket(double upperPrice, double lowerPrice)
{
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   
   // 1. Place Buy Stop above Range
   double buySL = upperPrice - (InpRiskDistancePoints * point);
   m_trade.BuyStop(InpLotSize, upperPrice, _Symbol, buySL, 0, ORDER_TIME_GTC, 0, "NEXUS_OCO_BUY");
   g_buyStopTicket = m_trade.ResultOrder();

   // 2. Place Sell Stop below Range
   double sellSL = lowerPrice + (InpRiskDistancePoints * point);
   m_trade.SellStop(InpLotSize, lowerPrice, _Symbol, sellSL, 0, ORDER_TIME_GTC, 0, "NEXUS_OCO_SELL");
   g_sellStopTicket = m_trade.ResultOrder();

   PrintFormat("[NEXUS MQL5] Symmetrical Bracket Placed: BuyStop=#%I64u @ %f | SellStop=#%I64u @ %f",
               g_buyStopTicket, upperPrice, g_sellStopTicket, lowerPrice);
}

//+------------------------------------------------------------------+
//| Low-Latency Trade Transaction Hook (Sub-Millisecond OCO Purge)    |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest& request,
                        const MqlTradeResult& result)
{
   // Check when a pending order transitions to a real position deal
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      if(HistoryDealSelect(trans.deal))
      {
         ulong dealMagic = HistoryDealGetInteger(trans.deal, DEAL_MAGIC);
         if(dealMagic != InpMagicNumber) return;

         long entryType = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
         if(entryType == DEAL_ENTRY_IN)
         {
            g_activeTicket    = HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
            g_positionActive  = true;
            g_harvestExecuted = false;

            PrintFormat("[NEXUS MQL5] Execution Fired: Position #%I64u Active! Purging Opposing Bracket...", g_activeTicket);
            PurgeOpposingPendingOrders();
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Instant Purge of Contrary Pending Orders                         |
//+------------------------------------------------------------------+
void PurgeOpposingPendingOrders()
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      if(m_order.SelectByIndex(i))
      {
         if(m_order.Magic() == InpMagicNumber && m_order.Symbol() == _Symbol)
         {
            ENUM_ORDER_TYPE type = m_order.OrderType();
            if(type == ORDER_TYPE_BUY_STOP || type == ORDER_TYPE_SELL_STOP)
            {
               ulong ticketToDelete = m_order.Ticket();
               m_trade.OrderDelete(ticketToDelete);
               PrintFormat("[NEXUS MQL5] 🛡️ OPPOSING ORDER #%I64u PURGED CLEANLY.", ticketToDelete);
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| High-Frequency Protection & Micro-Harvest Timer                  |
//+------------------------------------------------------------------+
void OnTimer()
{
   if(!g_positionActive || g_harvestExecuted) return;

   if(!m_position.SelectByTicket(g_activeTicket))
   {
      // Position no longer open
      g_positionActive = false;
      return;
   }

   double openPrice    = m_position.PriceOpen();
   double currentPrice = m_position.PriceCurrent();
   double slPrice      = m_position.StopLoss();
   double point        = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   double riskDistance = MathAbs(openPrice - slPrice);
   if(riskDistance <= 0.0) return;

   double gainDistance = (m_position.PositionType() == POSITION_TYPE_BUY) ? 
                         (currentPrice - openPrice) : (openPrice - currentPrice);

   double currentR = gainDistance / riskDistance;

   // Check if Target Scalp R-Multiple Reached
   if(currentR >= InpTargetHarvestR && !g_harvestExecuted)
   {
      ExecuteProfitProtection(openPrice, point);
   }
}

//+------------------------------------------------------------------+
//| Dual Execution: Bank 60% Volume + Lock Zero-Downside Breakeven   |
//+------------------------------------------------------------------+
void ExecuteProfitProtection(double openPrice, double point)
{
   double originalVol = m_position.Volume();
   double closeVol    = NormalizeDouble(originalVol * InpHarvestRatio, 2);

   // Step 1: Liquidate partial scalp volume
   if(m_trade.PositionClosePartial(g_activeTicket, closeVol))
   {
      PrintFormat("[NEXUS MQL5] 🚀 SCALP BANKED: %0.2f Lots closed on Ticket #%I64u.", closeVol, g_activeTicket);

      // Step 2: Lock remaining volume to Breakeven + Spread Cushion
      double beSL = 0.0;
      if(m_position.PositionType() == POSITION_TYPE_BUY)
         beSL = openPrice + (InpBufferPoints * point);
      else
         beSL = openPrice - (InpBufferPoints * point);

      if(m_trade.PositionModify(g_activeTicket, beSL, m_position.TakeProfit()))
      {
         PrintFormat("[NEXUS MQL5] 🛡️ POSITION IMMUNIZED: Ticket #%I64u SL set to %f (Risk-Free).", g_activeTicket, beSL);
         g_harvestExecuted = true;
      }
   }
}