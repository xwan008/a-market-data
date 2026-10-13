import {validSnapshots} from './model.js';

// UI-only leader: merge positions with formal handoff, use real quotes in the same intraday slot.
export function selectTodayLeader({monitor,buy,portfolio,holdingCharts,holdingSnapshot,status,tradeDate}={}){
 const empty={leader:null,poolCount:0,coveredCount:0,slot:null};
 if(!/^\d{4}-\d{2}-\d{2}$/.test(String(tradeDate||'')))return empty;
 const fresh=t=>typeof t==='string'&&t.startsWith(tradeDate)&&Number.isFinite(Date.parse(t));
 const positive=n=>typeof n==='number'&&Number.isFinite(n)&&n>0;
 const scanSlot=t=>{
  if(!fresh(t))return null;
  const d=new Date(t),m=((d.getUTCHours()+8)%24)*60+d.getUTCMinutes();
  return m>=570&&m<625?1:m>=625&&m<690?2:m>=780&&m<850?3:m>=850&&m<900?4:null;
 };
 const pool=new Map();
 const join=(item,type)=>{
  const code=String(item?.code||'').trim();if(!/^\d{6}$/.test(code))return;
  const prev=pool.get(code)||{code,name:code,trendName:'',inHolding:false,inHandoff:false};
  if(type==='holding'){prev.inHolding=true;prev.name=item.name||prev.name}
  else {prev.inHandoff=true;prev.name=item.company_name||prev.name;prev.trendName=item.trend_name||prev.trendName}
  pool.set(code,prev);
 };
 if(status?.airtable==='OK')for(const p of (Array.isArray(portfolio?.positions)?portfolio.positions:[]))
  if(p?.verified===true&&Number.isFinite(p.shares)&&p.shares>0)join(p,'holding');
 const monitoring=status?.monitor==='OK'&&monitor?.result_kind==='a_share_intraday_monitor_state'&&monitor.trade_date===tradeDate;
 const formal=status?.buyHandoff==='OK'&&Array.isArray(buy?.items)&&typeof buy.trade_date==='string'&&buy.trade_date<=tradeDate;
 for(const p of formal?buy.items:monitoring?(monitor.frozen_trend_buy_stocks||[]):[])join(p,'handoff');
 const quoteOK=holdingSnapshot?.result_kind==='a_share_intraday_market_snapshot'&&holdingSnapshot.trade_date===tradeDate&&holdingSnapshot.validation?.status==='passed';
 const chartOK=holdingCharts?.result_kind==='a_share_holding_charts'&&holdingCharts.trade_date===tradeDate;
 const frozen=new Map(monitoring?(monitor.frozen_trend_buy_stocks||[]).map(p=>[p.code,p]):[]);
 const candidates=[];
 for(const stock of pool.values()){
  const slots=new Map();
  const accept=(row,declaredSlot=null)=>{
   const slot=scanSlot(row?.scan_at);
   if(slot==null||(declaredSlot!=null&&slot!==declaredSlot)||!positive(row?.price)||typeof row.change_pct!=='number'||!Number.isFinite(row.change_pct))return;
   const point={slot,scan_at:row.scan_at,price:row.price,change_pct:row.change_pct};
   if(!slots.has(slot)||Date.parse(point.scan_at)>Date.parse(slots.get(slot).scan_at))slots.set(slot,point);
  };
  if(monitoring)for(const row of validSnapshots(monitor.stock_history?.[stock.code],tradeDate)){
   accept(row);
   if(!stock.trendName&&row.trend_name)stock.trendName=row.trend_name;
   if(stock.name===stock.code&&row.company_name)stock.name=row.company_name;
  }
  if(!stock.trendName)stock.trendName=frozen.get(stock.code)?.trend_name||'';
  if(stock.inHolding&&quoteOK){
   const quote=holdingSnapshot.holding_stocks?.[stock.code];
   if(quote?.code===stock.code&&quote.source_scope==='holding_watchlist'&&
    ['high','medium'].includes(quote.confidence)&&fresh(quote.quote_time)&&positive(quote.prev_close)){
    if(chartOK)for(const row of (Array.isArray(holdingCharts.stocks?.[stock.code]?.intraday_points)?holdingCharts.stocks[stock.code].intraday_points:[])){
     if(!Number.isInteger(row?.slot)||row.slot<1||row.slot>4||!positive(row.price))continue;
     accept({...row,change_pct:(row.price/quote.prev_close-1)*100},row.slot);
    }
    if(positive(quote.price)&&fresh(holdingSnapshot.captured_at))
     accept({scan_at:holdingSnapshot.captured_at,price:quote.price,change_pct:(quote.price/quote.prev_close-1)*100});
   }
  }
  const scans=[...slots.values()].sort((a,b)=>a.slot-b.slot);
  if(scans.length)candidates.push({...stock,scans,last:scans.at(-1)});
 }
 const slot=candidates.length?Math.max(...candidates.map(p=>p.last.slot)):null;
 const available=candidates.filter(p=>p.last.slot===slot).sort((a,b)=>b.last.change_pct-a.last.change_pct||a.code.localeCompare(b.code));
 return {leader:available[0]||null,poolCount:pool.size,coveredCount:available.length,slot};
}
