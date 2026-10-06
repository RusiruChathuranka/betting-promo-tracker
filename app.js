let data=[];

const $=id=>document.getElementById(id);

function money(v){
  return v==null?"—":"LKR "+Number(v).toLocaleString();
}
function pct(v){
  return v==null?"—":v+"%";
}
function titleCase(v){
  return String(v||"").replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase());
}

function counterPromo(group){
  const target="BETSS";
  const rivals=group.filter(x=>x.platform!==target).sort((a,b)=>b.score-a.score);
  const ref=rivals[0] || [...group].sort((a,b)=>b.score-a.score)[0];
  if(!ref) return null;

  const category=ref.category;
  const parts=[];
  let headline="";
  const bonus=ref.bonus_percent;
  const max=ref.max_bonus_lkr;
  const wager=ref.wagering_x;
  const minDep=ref.min_deposit_lkr;

  if(category==="cashback"){
    const suggested=bonus!=null ? Math.min(20,Math.round((bonus+1.5)*10)/10) : 6;
    headline="Offer "+suggested+"% cashback";
    parts.push(suggested+"% cashback");
    if(minDep!=null) parts.push("minimum qualifying deposit ≤ "+money(Math.max(0,Math.round(minDep*0.75))));
    parts.push("prefer real-cash credit with 1x or lower rollover where commercially viable");
  }else if(category==="new_customer"){
    const suggested=bonus!=null ? Math.round(bonus+10) : 50;
    headline=suggested+"% First Deposit / Welcome Bonus";
    parts.push(suggested+"% bonus");
    if(max!=null) parts.push("cap around "+money(Math.round(max*1.1/1000)*1000));
    if(minDep!=null) parts.push("minimum deposit ≤ "+money(Math.max(500,Math.round(minDep*0.75/100)*100)));
    if(wager!=null) parts.push("wagering ≤ "+Math.max(1,Math.ceil(wager-1))+"x");
  }else if(category==="reload_bonus" || category==="deposit_bonus" || category==="sports_bonus"){
    const suggested=bonus!=null ? Math.round(bonus+10) : 50;
    headline=suggested+"% "+titleCase(category).replace(" Bonus","")+" Counter Offer";
    parts.push(suggested+"% bonus");
    if(max!=null) parts.push("cap ≥ "+money(Math.round(max*1.1/1000)*1000));
    if(wager!=null) parts.push("wagering ≤ "+Math.max(1,Math.ceil(wager-1))+"x");
    if(minDep!=null) parts.push("minimum deposit ≤ "+money(Math.max(500,Math.round(minDep*0.75/100)*100)));
  }else if(category==="free_bet"){
    headline="Stronger Free Bet";
    parts.push(max!=null ? "free bet value ≥ "+money(Math.round(max*1.1/1000)*1000) : "increase free-bet value by ~10%");
    parts.push("keep qualification simpler than the benchmark");
    if(wager!=null) parts.push("wagering ≤ "+Math.max(1,Math.ceil(wager-1))+"x");
  }else if(category==="racing_bonus"){
    headline="Racing Cashback / Bonus Counter Offer";
    parts.push(bonus!=null ? Math.round(bonus+5)+"% racing bonus" : "10% racing cashback");
    if(max!=null) parts.push("cap ≥ "+money(Math.round(max*1.1/1000)*1000));
    if(wager!=null) parts.push("wagering ≤ "+Math.max(1,Math.ceil(wager-1))+"x");
  }else{
    headline="Simpler + stronger comparable offer";
    if(bonus!=null) parts.push(Math.round(bonus+10)+"% bonus");
    if(max!=null) parts.push("cap ≥ "+money(Math.round(max*1.1/1000)*1000));
    if(wager!=null) parts.push("wagering ≤ "+Math.max(1,Math.ceil(wager-1))+"x");
  }

  return {
    headline,
    details:parts,
    rationale:"Benchmark: "+ref.platform+" — "+ref.title
  };
}

function render(){
  const q=$("search").value.toLowerCase();
  const cat=$("category").value;
  const plat=$("platform").value;

  const filtered=data.filter(x=>
    (!q||JSON.stringify(x).toLowerCase().includes(q)) &&
    (!cat||x.category===cat) &&
    (!plat||x.platform===plat)
  );

  $("count").textContent=filtered.length+" offers";

  const groups={};
  filtered.forEach(x=>(groups[x.cluster_key]??=[]).push(x));

  $("winners").innerHTML=Object.values(groups).map(g=>{
    const w=[...g].sort((a,b)=>b.score-a.score)[0];
    const cp=counterPromo(g);

    return '<article class="card">'+
      '<div class="tag">'+w.cluster_label+'</div>'+
      '<h3>'+w.platform+'</h3>'+
      '<div class="metric"><span>'+w.title+'</span><b class="score">'+w.score+'</b></div>'+
      '<div class="metric"><span>Bonus</span><b>'+pct(w.bonus_percent)+'</b></div>'+
      '<div class="metric"><span>Maximum</span><b>'+money(w.max_bonus_lkr)+'</b></div>'+
      '<div class="metric"><span>Wagering</span><b>'+(w.wagering_x??"—")+'x</b></div>'+
      (cp ? '<div class="counter">'+
        '<div class="counter-label">BETSS COUNTER-PROMO</div>'+
        '<strong>'+cp.headline+'</strong>'+
        '<ul>'+cp.details.map(x=>'<li>'+x+'</li>').join("")+'</ul>'+
        '<small>'+cp.rationale+'</small>'+
      '</div>' : "")+
    '</article>';
  }).join("")||'<div class="card">No matching promotions.</div>';

  $("rows").innerHTML=filtered.map(x=>'<tr>'+
    '<td><b>'+x.platform+'</b></td>'+
    '<td>'+x.title+'</td>'+
    '<td>'+titleCase(x.customer_type)+'</td>'+
    '<td>'+x.cluster_label+'</td>'+
    '<td>'+pct(x.bonus_percent)+'</td>'+
    '<td>'+money(x.max_bonus_lkr)+'</td>'+
    '<td>'+(x.wagering_x??"—")+'x</td>'+
    '<td>'+money(x.min_deposit_lkr)+'</td>'+
    '<td><b>'+x.score+'</b></td>'+
    '<td><a target="_blank" rel="noopener" href="'+x.source_url+'">Source ↗</a></td>'+
  '</tr>').join("");
}

async function init(){
  const r=await fetch("data/promotions.json");
  const j=await r.json();

  data=j.promotions||[];

  $("updated").textContent=j.updated_at
    ?"Updated "+new Date(j.updated_at).toLocaleString()
    :"Awaiting first scrape";

  $("offers").textContent=data.length;
  $("platforms").textContent=new Set(data.map(x=>x.platform)).size;
  $("clusters").textContent=new Set(data.map(x=>x.cluster_key)).size;
  $("errors").textContent=(j.errors||[]).length;

  [
    ["category",[...new Set(data.map(x=>x.category))]],
    ["platform",[...new Set(data.map(x=>x.platform))]]
  ].forEach(([id,vals])=>
    vals.sort().forEach(v=>{
      const o=document.createElement("option");
      o.value=v;
      o.textContent=titleCase(v);
      $(id).appendChild(o);
    })
  );

  render();
}

$("search").oninput=render;
$("category").onchange=render;
$("platform").onchange=render;
init();