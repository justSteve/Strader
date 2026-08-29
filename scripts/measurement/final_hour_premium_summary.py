"""Summarize final_hour_premium.py rows: premium outcome vs ES move, per leg. [st-g0jo]
RUN  .venv/bin/python3 scripts/measurement/final_hour_premium_summary.py <premium.jsonl>
"""
import json, sys, statistics as st
rows = [json.loads(l) for l in open(sys.argv[1])]
ok = [r for r in rows if "skip" not in r]
LEGS = ["put_itm10", "put_atm0", "put_otm10", "call_itm10", "call_atm0", "call_otm10"]
print(f"days={len(rows)} usable={len(ok)}")
def med(xs): return st.median(xs) if xs else float('nan')
def pct(xs): return f"{sum(xs)/len(xs):.0%}" if xs else "-"
def corr(xs, ys):
    n=len(xs); mx=sum(xs)/n; my=sum(ys)/n
    sxy=sum((x-mx)*(y-my) for x,y in zip(xs,ys)); sx=sum((x-mx)**2 for x in xs)**.5; sy=sum((y-my)**2 for y in ys)**.5
    return sxy/(sx*sy) if sx and sy else float('nan')
BINS = [(-99,-10,"<-10 wrong big"),(-10,-5,"-10..-5"),(-5,0,"-5..0"),(0,5,"0..5"),(5,10,"5..10"),(10,15,"10..15"),(15,999,">=15 right big")]
for leg in LEGS:
    sign = -1 if leg.startswith("put") else 1
    S = [r for r in ok if "skip" not in r[leg]]
    L = [r[leg] for r in S]
    fav = [sign * r["es"]["close_chg"] for r in S]; favx = [r["es"]["fin_dn"] if sign<0 else r["es"]["fin_up"] for r in S]
    rc = [x["ret_close"] for x in L]; rm = [x["ret_mfe"] for x in L]
    print(f"\n==== {leg}  n={len(S)}  entry median {med([x['entry'] for x in L]):.2f}  noise floor median {med([x['noise_pts'] for x in L if x['noise_pts'] is not None]):.2f} pts  max print gap p90 {sorted([x['max_gap_s'] for x in L if x['max_gap_s']])[int(.9*len(L))-1]:.0f}s")
    print(f"  corr(ES fav net move, ret@close) {corr(fav, rc):+.2f}   corr(ES fav excursion, MFE) {corr(favx, rm):+.2f}")
    print(f"  ret@close median {med(rc):+.0%} mean {st.mean(rc):+.0%}  ret>0 {pct([x>0 for x in rc])}  >=+50% {pct([x>=.5 for x in rc])}  MFE>=+50% {pct([x>=.5 for x in rm])}")
    for key, lab in (("cut3","3% cut"),("cut10","10% cut"),("cut_30c","0.30 cut"),("cut_50c","0.50 cut")):
        c=[x[key] for x in L]
        print(f"  {lab:>9}: fired {pct([x['hit'] for x in c]):>4}  P/L median {med([x['ret'] for x in c]):+.0%} mean {st.mean([x['ret'] for x in c]):+.0%}  fired on right days(fav>=5) {pct([x['hit'] for x,f in zip(c,fav) if f>=5]):>4}  fired on wrong days(fav<=-5) {pct([x['hit'] for x,f in zip(c,fav) if f<=-5]):>4}")
    print("   ES fav move     n  ret@close  MFE    MAE   ret>0  >=+50%  0.30cut")
    for lo,hi,lab in BINS:
        g=[x for x,f in zip(L,fav) if lo<=f<hi]
        if not g: continue
        print(f"  {lab:>15} {len(g):3d}  {med([x['ret_close'] for x in g]):+7.0%} {med([x['ret_mfe'] for x in g]):+6.0%} {med([x['ret_mae'] for x in g]):+6.0%}  {pct([x['ret_close']>0 for x in g]):>5}  {pct([x['ret_close']>=.5 for x in g]):>5}  {pct([x['cut_30c']['hit'] for x in g]):>5}")
print("\n==== The asymmetry, per moneyness (right side = the side ES favoured at the close by >=5 pts)")
for m in ("itm10","atm0","otm10"):
    rs=[];ws=[]
    for r in ok:
        ch=r["es"]["close_chg"]
        if abs(ch)<5: continue
        right,wrong=(f"put_{m}",f"call_{m}") if ch<0 else (f"call_{m}",f"put_{m}")
        if "skip" in r[right] or "skip" in r[wrong]: continue
        rs.append(r[right]); ws.append(r[wrong])
    print(f"  {m:>5} n={len(rs)}  RIGHT: ret@close med {med([x['ret_close'] for x in rs]):+.0%} mean {st.mean([x['ret_close'] for x in rs]):+.0%}  >=+25% {pct([x['ret_close']>=.25 for x in rs])}  >=+50% {pct([x['ret_close']>=.5 for x in rs])}  >=+100% {pct([x['ret_close']>=1 for x in rs])}  0.30-cut fired {pct([x['cut_30c']['hit'] for x in rs])}  | WRONG: ret@close med {med([x['ret_close'] for x in ws]):+.0%}  under 0.30 cut med {med([x['cut_30c']['ret'] for x in ws]):+.0%}  under 10% cut med {med([x['cut10']['ret'] for x in ws]):+.0%}")
