//+------------------------------------------------------------------+
//|                                              OrderBlockM15.mq4   |
//|          Order Block M15 avec biais multi-timeframe D1/H4/H1     |
//|                                    Voir SPEC.md pour les regles  |
//+------------------------------------------------------------------+
#property version   "1.00"
#property strict

//--- Symbole / identification
input string InpSymbol             = "";        // Symbole ("" = graphique courant)
input int    InpMagic              = 20260803;  // Magic number

//--- Biais multi-timeframe
input int    InpBiasMAPeriod       = 50;        // Periode EMA du biais
input int    InpMinBiasAgreement   = 3;         // TF devant s'accorder (1-3)

//--- Structure M15
input int    InpFractalBars        = 2;         // Bougies de chaque cote d'un swing
input int    InpStructureLookback  = 200;       // Profondeur de scan M15
input int    InpOBSearchBars       = 30;        // Recherche de l'OB en amont du BOS
input int    InpMaxOBAgeBars       = 96;        // Peremption de l'OB (bougies M15)

//--- Risque
input double InpOBBufferATR        = 0.2;       // Marge du stop, en ATR(14) M15
input double InpRiskPercent        = 0.5;       // Risque par trade (% equite)
input double InpRewardRatio        = 2.0;       // Multiple de R vise
input double InpBreakEvenR         = 1.0;       // Break-even a xR (0 = desactive)
input int    InpMaxSpreadPoints    = 50;        // Spread maximum tolere (points)
input int    InpSlippagePoints     = 5;         // Slippage autorise (points)
input bool   InpOneTradeAtATime    = true;      // Une seule position ouverte

//--- Etat interne
string   gSymbol;
double   gPoint;
int      gDigits;
datetime gLastBarTime  = 0;   // derniere bougie M15 traitee
datetime gLastOBTraded = 0;   // horodatage de l'OB ayant deja servi

//--- Description d'un Order Block
struct OrderBlockInfo
  {
   bool     found;
   int      direction;     // +1 haussier, -1 baissier
   double   high;
   double   low;
   datetime formedTime;
   int      shift;         // decalage de la bougie OB au moment du scan
  };

//--- Order Block arme sur la derniere bougie M15 clôturee.
//    Recalcule une fois par bougie, surveille a chaque tick.
OrderBlockInfo gArmed;

//+------------------------------------------------------------------+
//| Initialisation                                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   gSymbol      = (StringLen(InpSymbol) > 0) ? InpSymbol : Symbol();
   gArmed.found = false;

   gPoint  = MarketInfo(gSymbol, MODE_POINT);
   gDigits = (int)MarketInfo(gSymbol, MODE_DIGITS);

   if(gPoint <= 0.0)
     {
      Print("Symbole introuvable ou non selectionne dans le Market Watch: ", gSymbol);
      return(INIT_FAILED);
     }

   if(InpMinBiasAgreement < 1 || InpMinBiasAgreement > 3)
     {
      Print("InpMinBiasAgreement doit etre compris entre 1 et 3.");
      return(INIT_PARAMETERS_INCORRECT);
     }

   if(InpFractalBars < 1)
     {
      Print("InpFractalBars doit etre >= 1.");
      return(INIT_PARAMETERS_INCORRECT);
     }

   if(InpRiskPercent <= 0.0 || InpRewardRatio <= 0.0)
     {
      Print("InpRiskPercent et InpRewardRatio doivent etre > 0.");
      return(INIT_PARAMETERS_INCORRECT);
     }

   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Tick                                                             |
//+------------------------------------------------------------------+
void OnTick()
  {
   // La gestion des positions ouvertes tourne a chaque tick.
   ManageOpenPositions();

   // L'analyse (biais, structure, Order Block) ne tourne qu'a l'ouverture d'une
   // bougie M15 : on ne raisonne que sur des bougies clôturees.
   datetime barTime = iTime(gSymbol, PERIOD_M15, 0);
   if(barTime != gLastBarTime)
     {
      gLastBarTime = barTime;
      RearmOrderBlock();
     }

   // Le declenchement, lui, est surveille a chaque tick : une mitigation peut
   // se produire au milieu d'une bougie et serait manquee sinon.
   if(!gArmed.found)
      return;

   if(gArmed.formedTime == gLastOBTraded)   // OB deja exploite
      return;

   if(InpOneTradeAtATime && CountOwnPositions() > 0)
      return;

   if(!PriceIsInsideZone(gArmed.direction, gArmed))
      return;

   if(SpreadPoints() > InpMaxSpreadPoints)
     {
      Print("Entree annulee: spread ", SpreadPoints(), " > ", InpMaxSpreadPoints, " points.");
      return;
     }

   if(OpenTrade(gArmed.direction, gArmed))
     {
      gLastOBTraded = gArmed.formedTime;
      gArmed.found  = false;
     }
  }

//+------------------------------------------------------------------+
//| Recalcul du biais et de l'Order Block actif                      |
//+------------------------------------------------------------------+
void RearmOrderBlock()
  {
   gArmed.found = false;

   int bias = GlobalBias();
   if(bias == 0)
      return;

   OrderBlockInfo ob;
   if(FindActiveOrderBlock(bias, ob))
      gArmed = ob;
  }

//+------------------------------------------------------------------+
//| Biais d'un timeframe, sur bougies clôturees uniquement           |
//+------------------------------------------------------------------+
int TimeframeBias(const int timeframe)
  {
   if(iBars(gSymbol, timeframe) < InpBiasMAPeriod + 3)
      return(0);

   double ma1   = iMA(gSymbol, timeframe, InpBiasMAPeriod, 0, MODE_EMA, PRICE_CLOSE, 1);
   double ma2   = iMA(gSymbol, timeframe, InpBiasMAPeriod, 0, MODE_EMA, PRICE_CLOSE, 2);
   double close = iClose(gSymbol, timeframe, 1);

   if(ma1 <= 0.0 || ma2 <= 0.0 || close <= 0.0)
      return(0);

   if(close > ma1 && ma1 > ma2)
      return(1);
   if(close < ma1 && ma1 < ma2)
      return(-1);

   return(0);
  }

//+------------------------------------------------------------------+
//| Biais global D1 + H4 + H1                                        |
//+------------------------------------------------------------------+
int GlobalBias()
  {
   int biases[3];
   biases[0] = TimeframeBias(PERIOD_D1);
   biases[1] = TimeframeBias(PERIOD_H4);
   biases[2] = TimeframeBias(PERIOD_H1);

   int bullish = 0, bearish = 0;
   for(int i = 0; i < 3; i++)
     {
      if(biases[i] > 0) bullish++;
      if(biases[i] < 0) bearish++;
     }

   // Accord suffisant ET aucune contradiction.
   if(bullish >= InpMinBiasAgreement && bearish == 0)
      return(1);
   if(bearish >= InpMinBiasAgreement && bullish == 0)
      return(-1);

   return(0);
  }

//+------------------------------------------------------------------+
//| Le bar 'shift' est-il un swing haut confirme ?                   |
//+------------------------------------------------------------------+
bool IsSwingHigh(const int shift)
  {
   if(shift - InpFractalBars < 0)
      return(false);   // bougies de droite pas encore formees

   double pivot = iHigh(gSymbol, PERIOD_M15, shift);

   for(int k = 1; k <= InpFractalBars; k++)
     {
      if(iHigh(gSymbol, PERIOD_M15, shift + k) >= pivot) return(false);
      if(iHigh(gSymbol, PERIOD_M15, shift - k) >= pivot) return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| Le bar 'shift' est-il un swing bas confirme ?                    |
//+------------------------------------------------------------------+
bool IsSwingLow(const int shift)
  {
   if(shift - InpFractalBars < 0)
      return(false);

   double pivot = iLow(gSymbol, PERIOD_M15, shift);

   for(int k = 1; k <= InpFractalBars; k++)
     {
      if(iLow(gSymbol, PERIOD_M15, shift + k) <= pivot) return(false);
      if(iLow(gSymbol, PERIOD_M15, shift - k) <= pivot) return(false);
     }
   return(true);
  }

//+------------------------------------------------------------------+
//| Recherche du BOS le plus recent puis de son Order Block          |
//+------------------------------------------------------------------+
bool FindActiveOrderBlock(const int direction, OrderBlockInfo &ob)
  {
   ob.found      = false;
   ob.direction  = direction;
   ob.high       = 0.0;
   ob.low        = 0.0;
   ob.formedTime = 0;
   ob.shift      = -1;

   // Plafond de scan : le balayage lit jusqu'a lookback + 2*F bougies pour
   // confirmer un swing, et jusqu'a lookback + InpOBSearchBars pour retrouver
   // l'Order Block. Les deux doivent rester dans l'historique disponible.
   int available = iBars(gSymbol, PERIOD_M15);
   int margin    = InpOBSearchBars + 2 * InpFractalBars + 2;
   int lookback  = InpStructureLookback;
   if(lookback > available - margin)
      lookback = available - margin;
   if(lookback < 20)
      return(false);

   double lastSwingHigh = 0.0;
   double lastSwingLow  = 0.0;
   int    bosShift      = -1;

   // Balayage du plus ancien vers le plus recent : le dernier BOS trouve gagne.
   for(int i = lookback; i >= 1; i--)
     {
      // Un swing situe InpFractalBars bougies plus loin est confirme a cet instant.
      int candidate = i + InpFractalBars;

      if(IsSwingHigh(candidate))
         lastSwingHigh = iHigh(gSymbol, PERIOD_M15, candidate);
      if(IsSwingLow(candidate))
         lastSwingLow = iLow(gSymbol, PERIOD_M15, candidate);

      double close = iClose(gSymbol, PERIOD_M15, i);

      if(direction > 0 && lastSwingHigh > 0.0 && close > lastSwingHigh)
        {
         bosShift      = i;
         lastSwingHigh = 0.0;   // structure consommee, on attend le swing suivant
        }
      else if(direction < 0 && lastSwingLow > 0.0 && close < lastSwingLow)
        {
         bosShift     = i;
         lastSwingLow = 0.0;
        }
     }

   if(bosShift < 0)
      return(false);

   // Remontee vers le passe depuis le BOS pour trouver la bougie d'origine.
   int obShift = -1;
   for(int j = bosShift + 1; j <= bosShift + InpOBSearchBars; j++)
     {
      double o = iOpen(gSymbol, PERIOD_M15, j);
      double c = iClose(gSymbol, PERIOD_M15, j);

      if(direction > 0 && c < o) { obShift = j; break; }   // derniere bougie baissiere
      if(direction < 0 && c > o) { obShift = j; break; }   // derniere bougie haussiere
     }

   if(obShift < 0)
      return(false);

   if(obShift > InpMaxOBAgeBars)
      return(false);   // zone perimee

   double obHigh = iHigh(gSymbol, PERIOD_M15, obShift);
   double obLow  = iLow(gSymbol, PERIOD_M15, obShift);

   // Invalidation : une clôture au-dela de la zone annule l'Order Block.
   for(int b = obShift - 1; b >= 1; b--)
     {
      double c = iClose(gSymbol, PERIOD_M15, b);
      if(direction > 0 && c < obLow)  return(false);
      if(direction < 0 && c > obHigh) return(false);
     }

   ob.found      = true;
   ob.high       = obHigh;
   ob.low        = obLow;
   ob.formedTime = iTime(gSymbol, PERIOD_M15, obShift);
   ob.shift      = obShift;

   return(true);
  }

//+------------------------------------------------------------------+
//| Le prix courant est-il dans la zone ?                            |
//+------------------------------------------------------------------+
bool PriceIsInsideZone(const int direction, const OrderBlockInfo &ob)
  {
   if(direction > 0)
     {
      double ask = MarketInfo(gSymbol, MODE_ASK);
      return(ask <= ob.high && ask >= ob.low);
     }

   double bid = MarketInfo(gSymbol, MODE_BID);
   return(bid >= ob.low && bid <= ob.high);
  }

//+------------------------------------------------------------------+
//| Ouverture de position                                            |
//+------------------------------------------------------------------+
bool OpenTrade(const int direction, const OrderBlockInfo &ob)
  {
   double atr = iATR(gSymbol, PERIOD_M15, 14, 1);
   if(atr <= 0.0)
      atr = 10 * gPoint;

   double buffer = InpOBBufferATR * atr;

   double entry, stop, target;

   if(direction > 0)
     {
      entry  = MarketInfo(gSymbol, MODE_ASK);
      stop   = ob.low - buffer;
      if(stop >= entry) return(false);
      target = entry + InpRewardRatio * (entry - stop);
     }
   else
     {
      entry  = MarketInfo(gSymbol, MODE_BID);
      stop   = ob.high + buffer;
      if(stop <= entry) return(false);
      target = entry - InpRewardRatio * (stop - entry);
     }

   // Respect de la distance minimale imposee par le courtier.
   double minStop = MarketInfo(gSymbol, MODE_STOPLEVEL) * gPoint;
   if(MathAbs(entry - stop) < minStop || MathAbs(entry - target) < minStop)
     {
      Print("Entree annulee: stop ou objectif trop proche du prix (STOPLEVEL = ",
            DoubleToStr(minStop, gDigits), ").");
      return(false);
     }

   double lots = CalculateLots(MathAbs(entry - stop));
   if(lots <= 0.0)
     {
      Print("Entree annulee: taille de position calculee nulle.");
      return(false);
     }

   int cmd = (direction > 0) ? OP_BUY : OP_SELL;

   int ticket = OrderSend(gSymbol,
                          cmd,
                          lots,
                          NormalizeDouble(entry, gDigits),
                          InpSlippagePoints,
                          NormalizeDouble(stop, gDigits),
                          NormalizeDouble(target, gDigits),
                          "OB M15",
                          InpMagic,
                          0,
                          (direction > 0) ? clrGreen : clrRed);

   if(ticket < 0)
     {
      Print("OrderSend a echoue, erreur ", GetLastError());
      return(false);
     }

   Print("Entree ", (direction > 0 ? "achat" : "vente"),
         " ", DoubleToStr(lots, 2), " lots",
         " | zone [", DoubleToStr(ob.low, gDigits), " ; ", DoubleToStr(ob.high, gDigits), "]",
         " | SL ", DoubleToStr(stop, gDigits),
         " | TP ", DoubleToStr(target, gDigits));

   return(true);
  }

//+------------------------------------------------------------------+
//| Taille de position pour un risque fixe en % de l'equite          |
//+------------------------------------------------------------------+
double CalculateLots(const double stopDistance)
  {
   if(stopDistance <= 0.0)
      return(0.0);

   double tickValue = MarketInfo(gSymbol, MODE_TICKVALUE);
   double tickSize  = MarketInfo(gSymbol, MODE_TICKSIZE);
   if(tickValue <= 0.0 || tickSize <= 0.0)
      return(0.0);

   double riskMoney    = AccountEquity() * InpRiskPercent / 100.0;
   double lossPerLot   = (stopDistance / tickSize) * tickValue;
   if(lossPerLot <= 0.0)
      return(0.0);

   double lots = riskMoney / lossPerLot;

   double minLot  = MarketInfo(gSymbol, MODE_MINLOT);
   double maxLot  = MarketInfo(gSymbol, MODE_MAXLOT);
   double lotStep = MarketInfo(gSymbol, MODE_LOTSTEP);

   if(lotStep > 0.0)
      lots = MathFloor(lots / lotStep) * lotStep;

   if(lots < minLot)
      return(0.0);   // risque trop faible pour le lot minimum : on s'abstient
   if(lots > maxLot)
      lots = maxLot;

   return(NormalizeDouble(lots, 2));
  }

//+------------------------------------------------------------------+
//| Positions ouvertes appartenant a cet EA                          |
//+------------------------------------------------------------------+
int CountOwnPositions()
  {
   int count = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderSymbol() != gSymbol || OrderMagicNumber() != InpMagic)
         continue;
      if(OrderType() == OP_BUY || OrderType() == OP_SELL)
         count++;
     }
   return(count);
  }

//+------------------------------------------------------------------+
//| Gestion des positions : mise a break-even                        |
//+------------------------------------------------------------------+
void ManageOpenPositions()
  {
   if(InpBreakEvenR <= 0.0)
      return;

   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES))
         continue;
      if(OrderSymbol() != gSymbol || OrderMagicNumber() != InpMagic)
         continue;

      double entry = OrderOpenPrice();
      double stop  = OrderStopLoss();
      if(stop <= 0.0)
         continue;

      if(OrderType() == OP_BUY)
        {
         double risk = entry - stop;
         if(risk <= 0.0) continue;
         if(stop >= entry) continue;   // deja au break-even ou au-dela

         double bid = MarketInfo(gSymbol, MODE_BID);
         if(bid >= entry + InpBreakEvenR * risk)
            MoveStopTo(entry);
        }
      else if(OrderType() == OP_SELL)
        {
         double risk = stop - entry;
         if(risk <= 0.0) continue;
         if(stop <= entry) continue;

         double ask = MarketInfo(gSymbol, MODE_ASK);
         if(ask <= entry - InpBreakEvenR * risk)
            MoveStopTo(entry);
        }
     }
  }

//+------------------------------------------------------------------+
//| Deplacement du stop de l'ordre selectionne                       |
//+------------------------------------------------------------------+
void MoveStopTo(const double newStop)
  {
   bool ok = OrderModify(OrderTicket(),
                         OrderOpenPrice(),
                         NormalizeDouble(newStop, gDigits),
                         OrderTakeProfit(),
                         0,
                         clrBlue);
   if(!ok)
      Print("OrderModify (break-even) a echoue, erreur ", GetLastError());
   else
      Print("Stop deplace au break-even sur le ticket ", OrderTicket());
  }

//+------------------------------------------------------------------+
//| Spread courant en points                                         |
//+------------------------------------------------------------------+
int SpreadPoints()
  {
   return((int)MarketInfo(gSymbol, MODE_SPREAD));
  }
//+------------------------------------------------------------------+
