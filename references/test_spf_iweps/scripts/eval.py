import sys,json,pandas as pd,numpy as np
S=sys.argv[1]; P=sys.argv[2]
St=pd.read_csv('stocks_spf_categories.csv',index_col=[0,1])
tab=pd.read_csv('table_natures_categories.csv')
q=pd.read_csv(f'{P}/data/processed/artif_communes_stock_annuel.csv').rename(columns={'annee_stock_1er_janvier':'an'})
c=pd.read_csv(f'{P}/data/processed/artif_communes_conso_annuelle.csv')
names=c.drop_duplicates('code_ins').set_index('code_ins').commune
spf=St['artif'].unstack(0).sort_index()
fs=spf.diff().shift(-1)   # flux annee N = S(N+1)-S(N)
sb=c.pivot_table(index='annee',columns='code_ins',values='conso_nette_ha')
atol=pd.DataFrame(json.load(open(f'{S}/atol_sample.json',encoding='utf-8'))).astype(float); atol.index=atol.index.astype(int); atol.columns=atol.columns.astype(int)
print('ATOL',atol.shape,atol.index.min(),atol.index.max())
yrs=[y for y in range(2011,2022)]
def stats(est,label,yrs=yrs):
    com=[k for k in atol.columns if k in est.columns]
    a=atol.loc[yrs,com]; b=est.loc[yrs,com]
    e=(b-a)
    rs=[a[k].corr(b[k]) for k in com]
    cum=(b.sum()-a.sum())
    print(f'{label}: n={len(com)} |e| annuel med {e.abs().stack().median():.2f} moy {e.abs().stack().mean():.2f} >1ha {100*(e.abs().stack()>1).mean():.0f}% r med {np.nanmedian(rs):.3f} | cumul {len(yrs)} ans: |e| med {cum.abs().median():.2f} ha, moy {cum.abs().mean():.2f}, biais {cum.mean():.2f} r {a.sum().corr(b.sum()):.3f}')
stats(fs,'SPF  ')
stats(sb,'Statbel')
for lag in (-1,1):
    stats(fs.shift(lag),f'SPF lag {lag}',yrs=[y for y in range(2012,2021)])
stats(fs,'SPF 2012-2020',yrs=list(range(2012,2021)))
stats(sb,'Stat 2012-2020',yrs=list(range(2012,2021)))
for k,n in [(52055,'?')]: pass
for nm in ['Anderlues','Seraing','Courcelles','Herstal']:
    k=[i for i in names.index if names[i]==nm]
    if not k: continue
    k=k[0]
    if k in atol.columns:
        print(nm,'2012-2021 ATOL',round(atol.loc[2012:2021,k].sum(),1),'SPF',round(fs.loc[2012:2021,k].sum(),1),'Statbel',round(sb.loc[2012:2021,k].sum(),1), 'Her2016' if nm=='Herstal' else '', round(fs.loc[2016,k],1) if nm=='Herstal' else '', round(atol.loc[2016,k],1) if nm=='Herstal' else '')
# Flux communaux vs parts IWEPS sur longues periodes
iw=pd.read_csv('iweps_long.csv'); iw=iw[(iw.cat=='artif')&~iw.ins.isin([82003,82005])]
Ys=iw.pivot_table(index='an',columns='ins',values='val')
sup=q[q.an==2023].set_index('code_ins').superficie_ha
for a_,b_ in[(2011,2023),(2015,2023),(2018,2023)]:
    com=spf.columns
    di=(Ys.loc[b_,com]-Ys.loc[a_,com])*sup[com]/100
    ds=spf.loc[b_,com]-spf.loc[a_,com]
    db=(q[q.an==b_].set_index('code_ins').stock_artif_ha-q[q.an==a_].set_index('code_ins').stock_artif_ha)[com]
    print(a_,b_,'SPF-IWEPS |e| med',round((ds-di).abs().median(),2),'r',round(ds.corr(di),3),' Statbel-IWEPS |e| med',round((db-di).abs().median(),2),'r',round(db.corr(di),3),' arrondi equiv ha med',round((sup*0.05/100).median(),1))
# Stabilite annuelle: sauts SPF vs Statbel
print('flux annuel: part |flux|>20ha SPF',round((fs.loc[2011:2024].abs()>20).stack().mean()*100,1),'Statbel',round((sb.loc[2011:2024].abs()>20).stack().mean()*100,1), 'negatifs SPF',round((fs.loc[2011:2024]<0).stack().mean()*100,1),'Statbel',round((sb.loc[2011:2024]<0).stack().mean()*100,1))
b=pd.read_csv(f'{P}/data/processed/suivi_communes.csv')
# Trajectoires par bassin 2021-2024
com_b=b.set_index('code_ins').bassin_sdt
bs=pd.read_csv(f'{P}/data/processed/suivi_bassins.csv').set_index('bassin')
flows=fs.T.groupby(com_b).sum().T
rows=[]
for ba in [x for x in bs.index if x in flows.columns]:
    ref=bs.loc[ba,'moyenne_ref_ha_an']; tr=sum(ref*(2050-n)/29 for n in range(2021,2025)); tr25=tr+ref*25/29
    rows.append((ba,round(bs.loc[ba,'ratio_obs_traj'],2),round(flows.loc[2021:2024,ba].sum()),round(flows.loc[2021:2024,ba].sum()/tr,2),round(flows.loc[2025,ba]),round(ref*25/29),round(flows.loc[2021:2025,ba].sum()/tr25,2)))
print(pd.DataFrame(rows,columns=['bassin','ratio_statbel_21_24','cum21_24_spf','ratio_spf_21_24','flux25','plafond25','ratio_spf_21_25']).to_string(index=False))
# natures: contribution aux flux recents
d=pd.read_csv('spf_natures.csv'); 
art=['resid','comm','equip','loisirs','agri_bat','indus','carrieres','transport','autres_art']
m=tab.set_index('nature').categorie
w=d.groupby(['an','nat']).m2.sum().unstack(0).fillna(0)/1e4
w=w[w.index.map(m).isin(art)]
dd=pd.DataFrame({'23_25':w[2025]-w[2023],'25_26':w[2026]-w[2025],'20_25':w[2025]-w[2020]}).round(1)
dd['lib']=[str(tab.set_index('nature').libelle.get(n))[:28] for n in dd.index]
print(dd.sort_values('20_25',ascending=False).head(14).to_string()); print(dd.sort_values('20_25').head(8).to_string())
print('sum',dd[['23_25','25_26','20_25']].sum().to_dict())

at=atol
for nm in ['Anderlues','Seraing']:
    k=[i for i in names.index if names[i]==nm][0]
    print(nm,pd.DataFrame({'atol':at.loc[2011:2021,k],'spf':fs.loc[2011:2021,k].round(1)}).T.to_string())
    x=d[d.code_ins==k].groupby(['an','nat']).m2.sum().unstack(0).fillna(0)/1e4
    x=x[x.index.map(m).isin(art)]
    z=(x[2022]-x[2012]).sort_values(key=abs,ascending=False).head(6).round(1)
    print({f"{n}:{str(tab.set_index('nature').libelle.get(n))[:18]}":v for n,v in z.items()})
# test strict: table apprise sans les communes ATOL ni apres 2018
Xp=d.pivot_table(index=['code_ins','an'],columns='nat',values='m2',aggfunc='sum',fill_value=0)/1e4
