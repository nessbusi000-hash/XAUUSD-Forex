//+------------------------------------------------------------------+
//|                                                   SMC_ICT_EA.mq4 |
//|  Strategies #2 et #3 du projet XAUUSD-Forex                       |
//|                                                                   |
//|  #2 SMC POI Continuation : biais HTF (BOS/CHoCH) + Premium /      |
//|     Discount + Order Block / FVG non mitige + CHoCH LTF.          |
//|  #3 Liquidity Sweep Reversal : chasse aux stops sur equal highs / |
//|     equal lows + rejet + CHoCH LTF avec deplacement.              |
//|                                                                   |
//|  Le TP vise systematiquement la poche de liquidite opposee et le  |
//|  trade n'est pris que si le R:R disponible atteint InpMinRR.      |
//|                                                                   |
//|  AVERTISSEMENT : le backtest 2012-2022 de ces regles sur XAUUSD   |
//|  est NEGATIF (voir docs/BACKTEST_SMC.md). InpEnableTrading est    |
//|  donc a false par defaut : l'EA se contente d'alerter.            |
//+------------------------------------------------------------------+
#property copyright "XAUUSD-Forex"
#property version   "1.00"
#property strict

enum ENUM_SMC_MODE
  {
   SMC_S2_POI      = 0, // #2 POI Continuation seule
   SMC_S3_SWEEP    = 1, // #3 Liquidity Sweep seule
   SMC_BOTH        = 2  // les deux
  };

//--- Selection de la strategie
input ENUM_SMC_MODE InpMode            = SMC_BOTH;
input bool          InpEnableTrading   = false;   // false = alertes seulement
input bool          InpAllowLong       = true;
input bool          InpAllowShort      = true;

//--- Timeframes
input ENUM_TIMEFRAMES InpHTF           = PERIOD_H4;  // biais / order flow
input ENUM_TIMEFRAMES InpLTF           = PERIOD_M15; // execution

//--- Structure de marche
input int    InpSwingLeft              = 2;
input int    InpSwingRight             = 2;
input int    InpHtfLookback            = 400;  // bougies HTF analysees
input int    InpLtfLookback            = 400;  // bougies LTF analysees
input int    InpObLookback             = 12;   // recherche de l'OB avant le deplacement
input double InpDisplacementATR        = 1.0;  // amplitude mini du deplacement

//--- Setup
input double InpEquilibrium            = 0.5;  // frontiere Premium / Discount
input int    InpConfirmWindow          = 16;   // bougies LTF pour confirmer apres le tap
input int    InpSweepWindow            = 12;   // bougies LTF pour confirmer apres la chasse
input double InpSLBufferATR            = 0.5;  // marge derriere le High/Low de l'OB
input double InpMinRR                  = 3.0;  // R:R minimum SMC
input double InpMaxRR                  = 8.0;
input bool   InpUseKillzones           = false; // filtre horaire ICT
input int    InpLondonStart            = 9;    // heure serveur
input int    InpLondonEnd              = 12;
input int    InpNewYorkStart           = 14;
input int    InpNewYorkEnd             = 18;

//--- Risque
input double InpRiskPercent            = 1.0;  // % d'equity risque par trade
input double InpMinSLDollars           = 1.0;
input double InpMaxSLDollars           = 60.0;
input bool   InpUsePartial             = false; // prise partielle a 1R puis point mort
input double InpPartialAtR             = 1.0;
input double InpPartialPct             = 50.0;  // % du lot ferme a la partielle
input int    InpMaxSpreadPoints        = 50;
input int    InpSlippage               = 5;
input int    InpMagic                  = 20260805;

//--- Etat interne
datetime g_lastBarTime = 0;

struct SmcStructure
  {
   int      bias;            // 1 haussier, -1 baissier, 0 indefini
   double   rangeLow;
   double   rangeHigh;
   int      lastEventDir;
   string   lastEventKind;   // "BOS" ou "CHoCH"
   int      lastEventShift;  // shift de la bougie de cassure
   double   obLow;           // dernier Order Block dans le sens du biais
   double   obHigh;
   int      obShift;
   bool     obValid;
  };

//+------------------------------------------------------------------+
int OnInit()
  {
   Print("SMC_ICT_EA initialise | mode=", EnumToString(InpMode),
         " trading=", InpEnableTrading ? "ON" : "ALERTES SEULES");
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason) {}

//+------------------------------------------------------------------+
//| Une seule evaluation par bougie LTF close                        |
//+------------------------------------------------------------------+
void OnTick()
  {
   ManageOpenPositions();

   datetime t = iTime(_Symbol, InpLTF, 0);
   if(t == g_lastBarTime)
      return;
   g_lastBarTime = t;

   if(iBars(_Symbol, InpHTF) < InpHtfLookback + 10) return;
   if(iBars(_Symbol, InpLTF) < InpLtfLookback + 10) return;
   if(CountOwnOrders() > 0) return;
   if(MarketInfo(_Symbol, MODE_SPREAD) > InpMaxSpreadPoints) return;
   if(InpUseKillzones && !InKillzone()) return;

   if(InpMode == SMC_S2_POI || InpMode == SMC_BOTH)
      if(TryPoiContinuation()) return;
   if(InpMode == SMC_S3_SWEEP || InpMode == SMC_BOTH)
      TryLiquiditySweep();
  }

//+------------------------------------------------------------------+
//| Fractales                                                        |
//+------------------------------------------------------------------+
bool IsSwingHigh(ENUM_TIMEFRAMES tf, int shift)
  {
   if(shift - InpSwingRight < 0) return(false);
   double h = iHigh(_Symbol, tf, shift);
   for(int j = 1; j <= InpSwingLeft; j++)          // bougies plus anciennes
      if(iHigh(_Symbol, tf, shift + j) >= h) return(false);
   for(int k = 1; k <= InpSwingRight; k++)         // bougies plus recentes
      if(iHigh(_Symbol, tf, shift - k) > h) return(false);
   return(true);
  }

bool IsSwingLow(ENUM_TIMEFRAMES tf, int shift)
  {
   if(shift - InpSwingRight < 0) return(false);
   double l = iLow(_Symbol, tf, shift);
   for(int j = 1; j <= InpSwingLeft; j++)
      if(iLow(_Symbol, tf, shift + j) <= l) return(false);
   for(int k = 1; k <= InpSwingRight; k++)
      if(iLow(_Symbol, tf, shift - k) < l) return(false);
   return(true);
  }

//+------------------------------------------------------------------+
//| Structure de marche : BOS / CHoCH, dealing range, Order Block    |
//+------------------------------------------------------------------+
void ScanStructure(ENUM_TIMEFRAMES tf, int lookback, SmcStructure &st)
  {
   st.bias = 0; st.rangeLow = 0; st.rangeHigh = 0;
   st.lastEventDir = 0; st.lastEventKind = ""; st.lastEventShift = -1;
   st.obValid = false; st.obLow = 0; st.obHigh = 0; st.obShift = -1;

   double lastSwingHigh = 0.0, lastSwingLow = 0.0;
   double atr = iATR(_Symbol, tf, 14, 1);

   for(int i = lookback; i >= 1; i--)   // du plus ancien au plus recent
     {
      int k = i + InpSwingRight;        // pivot confirme par la bougie i
      if(k + InpSwingLeft < iBars(_Symbol, tf))
        {
         if(IsSwingHigh(tf, k)) lastSwingHigh = iHigh(_Symbol, tf, k);
         if(IsSwingLow(tf, k))  lastSwingLow  = iLow(_Symbol, tf, k);
        }

      double c = iClose(_Symbol, tf, i);

      if(lastSwingHigh > 0.0 && c > lastSwingHigh)
        {
         st.lastEventKind  = (st.bias == 1) ? "BOS" : "CHoCH";
         st.bias           = 1;
         st.lastEventDir   = 1;
         st.lastEventShift = i;
         st.rangeLow       = (lastSwingLow > 0.0) ? lastSwingLow : iLow(_Symbol, tf, iLowest(_Symbol, tf, MODE_LOW, 50, i));
         st.rangeHigh      = iHigh(_Symbol, tf, iHighest(_Symbol, tf, MODE_HIGH, 50, i));
         CaptureOrderBlock(tf, i, 1, atr, st);
         lastSwingHigh = 0.0;
        }
      else if(lastSwingLow > 0.0 && c < lastSwingLow)
        {
         st.lastEventKind  = (st.bias == -1) ? "BOS" : "CHoCH";
         st.bias           = -1;
         st.lastEventDir   = -1;
         st.lastEventShift = i;
         st.rangeHigh      = (lastSwingHigh > 0.0) ? lastSwingHigh : iHigh(_Symbol, tf, iHighest(_Symbol, tf, MODE_HIGH, 50, i));
         st.rangeLow       = iLow(_Symbol, tf, iLowest(_Symbol, tf, MODE_LOW, 50, i));
         CaptureOrderBlock(tf, i, -1, atr, st);
         lastSwingLow = 0.0;
        }

      // Extension du dealing range dans le sens de l'order flow.
      if(st.bias == 1)  st.rangeHigh = MathMax(st.rangeHigh, iHigh(_Symbol, tf, i));
      if(st.bias == -1) st.rangeLow  = MathMin(st.rangeLow,  iLow(_Symbol, tf, i));
     }

   if(st.obValid) st.obValid = !IsMitigated(tf, st);
  }

//+------------------------------------------------------------------+
//| Order Block : derniere bougie opposee avant le deplacement       |
//+------------------------------------------------------------------+
void CaptureOrderBlock(ENUM_TIMEFRAMES tf, int breakShift, int dir, double atr, SmcStructure &st)
  {
   for(int j = breakShift; j <= breakShift + InpObLookback; j++)
     {
      double o = iOpen(_Symbol, tf, j);
      double c = iClose(_Symbol, tf, j);
      bool candidate = (dir == 1) ? (c < o) : (c > o);
      if(!candidate) continue;

      double impulse;
      if(dir == 1)
         impulse = iHigh(_Symbol, tf, iHighest(_Symbol, tf, MODE_HIGH, j - breakShift + 1, breakShift)) - iLow(_Symbol, tf, j);
      else
         impulse = iHigh(_Symbol, tf, j) - iLow(_Symbol, tf, iLowest(_Symbol, tf, MODE_LOW, j - breakShift + 1, breakShift));

      if(atr > 0 && impulse < InpDisplacementATR * atr) return;

      st.obLow   = iLow(_Symbol, tf, j);
      st.obHigh  = iHigh(_Symbol, tf, j);
      st.obShift = j;
      st.obValid = true;
      return;
     }
  }

//--- Un OB deja traverse par le prix n'est plus exploitable.
bool IsMitigated(ENUM_TIMEFRAMES tf, SmcStructure &st)
  {
   for(int i = st.obShift - 1; i >= 1; i--)
     {
      if(st.bias == 1 && iClose(_Symbol, tf, i) < st.obLow)  return(true);
      if(st.bias == -1 && iClose(_Symbol, tf, i) > st.obHigh) return(true);
     }
   return(false);
  }

//+------------------------------------------------------------------+
//| Liquidite : sommets / creux intacts (BSL / SSL)                  |
//+------------------------------------------------------------------+
double NearestLiquidity(ENUM_TIMEFRAMES tf, int lookback, int side, double from,
                        double risk, double minRR, double maxRR)
  {
   double best = 0.0;
   double bestDist = 0.0;

   for(int i = InpSwingRight + 1; i <= lookback; i++)
     {
      double level;
      if(side > 0)
        {
         if(!IsSwingHigh(tf, i)) continue;
         level = iHigh(_Symbol, tf, i);
         if(level <= from) continue;
         // Intact : aucune bougie posterieure ne l'a depasse.
         int hi = iHighest(_Symbol, tf, MODE_HIGH, i, 1);
         if(iHigh(_Symbol, tf, hi) > level) continue;
        }
      else
        {
         if(!IsSwingLow(tf, i)) continue;
         level = iLow(_Symbol, tf, i);
         if(level >= from) continue;
         int lo = iLowest(_Symbol, tf, MODE_LOW, i, 1);
         if(iLow(_Symbol, tf, lo) < level) continue;
        }

      double rr = MathAbs(level - from) / risk;
      if(rr < minRR || rr > maxRR) continue;

      double dist = MathAbs(level - from);
      if(best == 0.0 || dist < bestDist) { best = level; bestDist = dist; }
     }
   return(best);
  }

//+------------------------------------------------------------------+
//| Strategie #2 : POI Continuation                                  |
//+------------------------------------------------------------------+
bool TryPoiContinuation()
  {
   SmcStructure htf, ltf;
   ScanStructure(InpHTF, InpHtfLookback, htf);
   ScanStructure(InpLTF, InpLtfLookback, ltf);

   if(htf.bias == 0 || !htf.obValid) return(false);
   if(htf.rangeHigh <= htf.rangeLow) return(false);

   // Confirmation : CHoCH LTF sur la bougie qui vient de se cloturer.
   if(ltf.lastEventShift != 1 || ltf.lastEventKind != "CHoCH") return(false);
   if(ltf.lastEventDir != htf.bias) return(false);

   double price = iClose(_Symbol, InpLTF, 1);
   double frac  = (price - htf.rangeLow) / (htf.rangeHigh - htf.rangeLow);
   double atr   = iATR(_Symbol, InpLTF, 14, 1);

   if(htf.bias == 1)
     {
      if(!InpAllowLong || frac > InpEquilibrium) return(false);           // achat en Discount uniquement
      if(!TappedZone(1, htf.obLow, htf.obHigh)) return(false);
      double lowest = iLow(_Symbol, InpLTF, iLowest(_Symbol, InpLTF, MODE_LOW, InpConfirmWindow, 1));
      double sl = MathMin(htf.obLow, lowest) - InpSLBufferATR * atr;
      return(OpenTrade(OP_BUY, sl, "S2-POI"));
     }

   if(!InpAllowShort || frac < 1.0 - InpEquilibrium) return(false);       // vente en Premium uniquement
   if(!TappedZone(-1, htf.obLow, htf.obHigh)) return(false);
   double highest = iHigh(_Symbol, InpLTF, iHighest(_Symbol, InpLTF, MODE_HIGH, InpConfirmWindow, 1));
   double sl2 = MathMax(htf.obHigh, highest) + InpSLBufferATR * atr;
   return(OpenTrade(OP_SELL, sl2, "S2-POI"));
  }

//--- Le prix a-t-il touche le POI dans la fenetre de confirmation ?
bool TappedZone(int dir, double zLow, double zHigh)
  {
   for(int i = 1; i <= InpConfirmWindow; i++)
     {
      if(dir == 1 && iLow(_Symbol, InpLTF, i) <= zHigh && iClose(_Symbol, InpLTF, i) >= zLow)
         return(true);
      if(dir == -1 && iHigh(_Symbol, InpLTF, i) >= zLow && iClose(_Symbol, InpLTF, i) <= zHigh)
         return(true);
     }
   return(false);
  }

//+------------------------------------------------------------------+
//| Strategie #3 : Liquidity Sweep Reversal                          |
//+------------------------------------------------------------------+
bool TryLiquiditySweep()
  {
   SmcStructure ltf, htf;
   ScanStructure(InpLTF, InpLtfLookback, ltf);
   ScanStructure(InpHTF, InpHtfLookback, htf);

   if(ltf.lastEventShift != 1) return(false);
   if(ltf.lastEventKind != "CHoCH" && ltf.lastEventKind != "BOS") return(false);

   double atr = iATR(_Symbol, InpLTF, 14, 1);
   if(atr <= 0) return(false);

   // Deplacement institutionnel exige sur la bougie de cassure.
   double range = iHigh(_Symbol, InpLTF, 1) - iLow(_Symbol, InpLTF, 1);
   if(range < InpDisplacementATR * atr) return(false);

   double price = iClose(_Symbol, InpLTF, 1);
   double frac = (htf.rangeHigh > htf.rangeLow)
                 ? (price - htf.rangeLow) / (htf.rangeHigh - htf.rangeLow) : 0.5;

   if(ltf.lastEventDir == -1)                       // vente apres chasse de BSL
     {
      if(!InpAllowShort || frac < 1.0 - InpEquilibrium) return(false);
      double sweepHigh = FindSweep(1, atr);
      if(sweepHigh <= 0.0) return(false);
      return(OpenTrade(OP_SELL, sweepHigh + InpSLBufferATR * atr, "S3-Sweep"));
     }

   if(!InpAllowLong || frac > InpEquilibrium) return(false);              // achat apres chasse de SSL
   double sweepLow = FindSweep(-1, atr);
   if(sweepLow <= 0.0) return(false);
   return(OpenTrade(OP_BUY, sweepLow - InpSLBufferATR * atr, "S3-Sweep"));
  }

//--- Cherche une chasse aux stops recente : depassement franc d'un
//--- sommet/creux structurel, suivi d'une cloture de l'autre cote.
double FindSweep(int side, double atr)
  {
   double tol = MathMax(0.15 * atr, iClose(_Symbol, InpLTF, 1) * 0.0001);

   for(int i = 1; i <= InpSweepWindow; i++)
     {
      for(int k = i + InpSwingRight + 1; k <= i + 60; k++)
        {
         double level;
         if(side > 0)
           {
            if(!IsSwingHigh(InpLTF, k)) continue;
            level = iHigh(_Symbol, InpLTF, k);
            if(iHigh(_Symbol, InpLTF, i) > level + tol && iClose(_Symbol, InpLTF, i) < level)
               return(iHigh(_Symbol, InpLTF, iHighest(_Symbol, InpLTF, MODE_HIGH, i, 1)));
           }
         else
           {
            if(!IsSwingLow(InpLTF, k)) continue;
            level = iLow(_Symbol, InpLTF, k);
            if(iLow(_Symbol, InpLTF, i) < level - tol && iClose(_Symbol, InpLTF, i) > level)
               return(iLow(_Symbol, InpLTF, iLowest(_Symbol, InpLTF, MODE_LOW, i, 1)));
           }
        }
     }
   return(0.0);
  }

//+------------------------------------------------------------------+
//| Execution                                                        |
//+------------------------------------------------------------------+
bool OpenTrade(int cmd, double sl, string tag)
  {
   RefreshRates();
   double entry = (cmd == OP_BUY) ? Ask : Bid;
   double risk  = MathAbs(entry - sl);

   if(risk < InpMinSLDollars || risk > InpMaxSLDollars) return(false);

   int side = (cmd == OP_BUY) ? 1 : -1;
   double tp = NearestLiquidity(InpHTF, InpHtfLookback, side, entry, risk, InpMinRR, InpMaxRR);
   if(tp == 0.0)
      tp = NearestLiquidity(InpLTF, InpLtfLookback, side, entry, risk, InpMinRR, InpMaxRR);
   if(tp == 0.0)
     {
      Print(tag, " ecarte : aucune poche de liquidite n'offre 1:", DoubleToStr(InpMinRR, 1));
      return(false);
     }

   double lots = CalcLots(risk);
   if(lots <= 0) return(false);

   double rr = MathAbs(tp - entry) / risk;
   string msg = StringConcatenate(
                   tag, " ", (cmd == OP_BUY ? "BUY" : "SELL"), " ", _Symbol,
                   " entry=", DoubleToStr(entry, 2),
                   " SL=", DoubleToStr(sl, 2),
                   " TP=", DoubleToStr(tp, 2),
                   " RR=1:", DoubleToStr(rr, 1),
                   " lots=", DoubleToStr(lots, 2));

   if(!InpEnableTrading)
     {
      Print("[SIGNAL] ", msg);
      Alert("[SMC] ", msg);
      return(true);
     }

   int ticket = OrderSend(_Symbol, cmd, lots, entry, InpSlippage,
                          NormalizeDouble(sl, _Digits), NormalizeDouble(tp, _Digits),
                          tag, InpMagic, 0, (cmd == OP_BUY ? clrGreen : clrRed));
   if(ticket < 0)
     {
      Print("OrderSend echoue (", GetLastError(), ") : ", msg);
      return(false);
     }
   Print("[TRADE] ", msg);
   return(true);
  }

double CalcLots(double slDistance)
  {
   double tickValue = MarketInfo(_Symbol, MODE_TICKVALUE);
   double tickSize  = MarketInfo(_Symbol, MODE_TICKSIZE);
   if(tickSize <= 0 || tickValue <= 0) return(0);

   double valuePerUnit = tickValue / tickSize;          // $ par 1.00 de prix et par lot
   double riskMoney    = AccountEquity() * InpRiskPercent / 100.0;
   double lots         = riskMoney / (slDistance * valuePerUnit);

   double step = MarketInfo(_Symbol, MODE_LOTSTEP);
   double minL = MarketInfo(_Symbol, MODE_MINLOT);
   double maxL = MarketInfo(_Symbol, MODE_MAXLOT);
   if(step > 0) lots = MathFloor(lots / step) * step;
   lots = MathMax(minL, MathMin(maxL, lots));
   return(NormalizeDouble(lots, 2));
  }

//+------------------------------------------------------------------+
//| Gestion : prise partielle a 1R + passage au point mort           |
//+------------------------------------------------------------------+
//| Le SL remonte au point mort apres la partielle : il sert aussi de |
//| marqueur d'idempotence (une position deja allegee a SL = entree). |
void ManageOpenPositions()
  {
   if(!InpEnableTrading || !InpUsePartial) return;

   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() != InpMagic || OrderSymbol() != _Symbol) continue;

      int    type  = OrderType();
      double entry = OrderOpenPrice();
      double sl    = OrderStopLoss();
      double tp    = OrderTakeProfit();
      double risk  = MathAbs(entry - sl);
      if(risk <= 0) continue;

      // Deja allegee (SL au point mort ou au-dela) : rien a faire.
      if(type == OP_BUY  && sl >= entry - _Point) continue;
      if(type == OP_SELL && sl <= entry + _Point) continue;

      RefreshRates();
      bool reached = (type == OP_BUY)
                     ? (Bid >= entry + InpPartialAtR * risk)
                     : (Ask <= entry - InpPartialAtR * risk);
      if(!reached) continue;

      double part = OrderLots() * InpPartialPct / 100.0;
      double step = MarketInfo(_Symbol, MODE_LOTSTEP);
      if(step > 0) part = MathFloor(part / step) * step;
      if(part < MarketInfo(_Symbol, MODE_MINLOT)) continue;
      if(OrderLots() - part < MarketInfo(_Symbol, MODE_MINLOT)) continue;

      double closePrice = (type == OP_BUY) ? Bid : Ask;
      if(!OrderClose(OrderTicket(), NormalizeDouble(part, 2), closePrice, InpSlippage, clrOrange))
        {
         Print("OrderClose partiel echoue : ", GetLastError());
         continue;
        }

      // MT4 recree le reliquat sous un nouveau ticket : on le retrouve par
      // magic + prix d'ouverture, puis on place le SL au point mort.
      MoveRemainderToBreakEven(type, entry, tp);
     }
  }

void MoveRemainderToBreakEven(int type, double entry, double tp)
  {
   for(int j = OrdersTotal() - 1; j >= 0; j--)
     {
      if(!OrderSelect(j, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() != InpMagic || OrderSymbol() != _Symbol) continue;
      if(OrderType() != type) continue;
      if(MathAbs(OrderOpenPrice() - entry) > _Point) continue;

      if(!OrderModify(OrderTicket(), OrderOpenPrice(), NormalizeDouble(entry, _Digits),
                      NormalizeDouble(tp, _Digits), 0, clrBlue))
         Print("OrderModify point mort echoue : ", GetLastError());
      return;
     }
  }

int CountOwnOrders()
  {
   int n = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderMagicNumber() == InpMagic && OrderSymbol() == _Symbol) n++;
     }
   return(n);
  }

bool InKillzone()
  {
   int h = TimeHour(TimeCurrent());
   if(h >= InpLondonStart && h < InpLondonEnd) return(true);
   if(h >= InpNewYorkStart && h < InpNewYorkEnd) return(true);
   return(false);
  }
//+------------------------------------------------------------------+
