import sys,json,pandas as pd,numpy as np
S=sys.argv[1]; P=sys.argv[2]
d=pd.read_csv('spf_natures.csv'); d.loc[d.name=='Bertogne','code_ins']=82039; d['code_ins']=d.code_ins.astype(int)
X=d.pivot_table(index=['code_ins','an'],columns='nat',values='m2',aggfunc='sum',fill_value=0)/1e4
q=pd.read_csv(f'{P}/data/processed/artif_communes_stock_annuel.csv').rename(columns={'annee_stock_1er_janvier':'an'})
sup=q.set_index(['code_ins','an']).superficie_ha
a=sup.xs(2025,level='an').to_frame('s'); a['an']=2026; sup=pd.concat([sup,a.reset_index().set_index(['code_ins','an']).s])
iw=pd.read_csv('iweps_long.csv'); iw=iw[~iw.ins.isin([82003,82005])]
Y=iw.pivot_table(index=['ins','an'],columns='cat',values='val'); Y.index.names=['code_ins','an']
idx=X.index.intersection(Y.index)
s=sup.reindex(idx); Yha=Y.loc[idx].mul(s,axis=0)/100
X2=X.copy(); X2['noncad']=(sup.reindex(X.index)-X.sum(axis=1)).clip(lower=0)
Xc=X2.loc[idx]
def nnls(A,b,it=400):
    G=A.T@A;c=A.T@b;x=np.zeros(A.shape[1]);g=np.maximum(np.diag(G),1e-9)
    for _ in range(it):
        for j in range(len(x)):
            x[j]=max(0,(c[j]-G[j]@x+G[j,j]*x[j])/g[j])
    return x
cats=[k for k in Y.columns if k!='artif']
A=Xc.values; keep=np.where(A.sum(axis=0)>0)[0]
coef=pd.DataFrame(0.0,index=Xc.columns,columns=cats)
for k in cats: coef.loc[Xc.columns[keep],k]=nnls(A[:,keep],Yha[k].values)
lab=json.load(open('labels.json',encoding='utf-8'))
# verification des natures recentes
for n in [555,558,165,551,538,554,539,370,557,559,164,166,407,70,78,4]:
    r=coef.loc[n].sort_values(ascending=False); print(n,lab.get(str(n),'')[:28],[(r.index[i],round(r.iloc[i],2)) for i in range(2)],'somme',round(r.sum(),2))
ov={}
def S_(c,*ns):
    for n in ns: ov[n]=c
S_('equip',480,481,482,483,484,485,486,487,488,489,426,420,433,431,506,505,509,508,463,462,421,422,423,424,425,440,461,430,372,373,374,375,22,429 if False else 22,550)
S_('comm',405,403,404,400,401,407,412,414,535,536,542,547,402)
S_('resid',555,166,164,165,538,551,552,553,541,556,557,558,559,79,201,223,220,221,532,533,534,537,543,544,545,546,549,222)
S_('indus',85,86,87,80,304,288,302,285,262,348,379,289,263,370,554,382,286,354,355)
S_('transport',428,429,52,34)
S_('autres_art',63,62,43,524,525,526,527,521,510,539,68)
S_('agri_bat',242,246)
S_('eau',28); S_('seminat',41,42); S_('herbe',7); S_('arable',12); S_('inconnu',170,540)
cols=[c for c in X.columns]
hard={}
for n in cols:
    if n in ov: hard[n]=ov[n]; continue
    r=coef.loc[n]; hard[n]=r.idxmax()
tab=pd.DataFrame({'nature':cols,'libelle':[lab.get(str(n),'') for n in cols],'categorie':[hard[n] for n in cols],'source':['libelle' if n in ov else 'donnees' for n in cols],'coef_max':[round(coef.loc[n].max(),3) for n in cols],'somme_coef':[round(coef.loc[n].sum(),3) for n in cols],'ha_2023':[round(X.xs(2023,level='an')[n].sum(),1) for n in cols]})
tab.to_csv('table_natures_categories.csv',index=False,encoding='utf-8-sig')
print(tab.groupby('source').ha_2023.agg(['count','sum']).round(0))
print('natures artif a faible signal, par surface:'); 
ART=['resid','comm','equip','loisirs','agri_bat','indus','carrieres','transport','autres_art']
M=pd.get_dummies(pd.Series(hard)).reindex(columns=cats,fill_value=0).astype(float)
P_=pd.DataFrame(X.values@M.loc[X.columns].values,index=X.index,columns=cats)
P_['inconnu']+= (sup.reindex(X.index)-X.sum(axis=1)).clip(lower=0)
P_['artif']=P_[ART].sum(axis=1)
P_.to_csv('stocks_spf_categories.csv')
# 1 stock
e=(P_['artif'].reindex(idx)-Yha['artif'])/s*100
print('STOCK artif pts: MAE',e.abs().mean().round(3),'med',e.abs().median().round(3),'p95',e.abs().quantile(.95).round(3),'max',e.abs().max().round(2),'biais',e.mean().round(3))
print('par annee',e.groupby(level=1).mean().round(3).to_dict())
print('par cat MAE',{k:round((((P_[k].reindex(idx)-Yha[k])/s*100).abs().mean()),3) for k in cats})
print('pires', e.abs().groupby(level=0).mean().sort_values(ascending=False).head(8).round(2).to_dict())
# 2 regional
W=P_['artif'].groupby(level=1).sum()
print('Wallonie stock ha',W.round(0).to_dict())
print('flux an ha',W.diff().shift(-1).round(0).to_dict())
for a_,b_,pub in [(2015,2020,11.2),(2020,2025,12.3),(2025,2026,10.5),(2011,2015,None)]:
    print(a_,b_,'SPF km2/an',round((W[b_]-W[a_])/(b_-a_)/100,2),'T005',pub)
st=q.groupby('an').stock_artif_ha.sum()
for a_,b_ in[(2015,2020),(2020,2025),(2011,2015)]: print('Statbel',a_,b_,round((st[b_]-st[a_])/(b_-a_)/100,2))
