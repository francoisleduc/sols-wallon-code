import sys,json,pandas as pd,numpy as np
S=sys.argv[1]; P=sys.argv[2]
d=pd.read_csv('spf_natures.csv'); d.loc[d.name=='Bertogne','code_ins']=82039; d['code_ins']=d.code_ins.astype(int)
X=d.pivot_table(index=['code_ins','an'],columns='nat',values='m2',aggfunc='sum',fill_value=0)/1e4
q=pd.read_csv(f'{P}/data/processed/artif_communes_stock_annuel.csv').rename(columns={'annee_stock_1er_janvier':'an'})
sup=q.set_index(['code_ins','an']).superficie_ha
a=sup.xs(2025,level='an').to_frame('s'); a['an']=2026; sup=pd.concat([sup,a.reset_index().set_index(['code_ins','an']).s])
iw=pd.read_csv('iweps_long.csv'); iw=iw[~iw.ins.isin([82003,82005])]
Y=iw.pivot_table(index=['ins','an'],columns='cat',values='val'); Y.index.names=['code_ins','an']
idx=X.index.intersection(Y.index); s=sup.reindex(idx); Yha=Y.loc[idx].mul(s,axis=0)/100
X2=X.copy(); X2['noncad']=(sup.reindex(X.index)-X.sum(axis=1)).clip(lower=0)
atol=pd.DataFrame(json.load(open(f'{S}/atol_sample.json',encoding='utf-8'))).astype(float); atol.index=atol.index.astype(int); atol.columns=atol.columns.astype(int)
c_=idx.get_level_values(0); y_=idx.get_level_values(1)
tr=(~c_.isin(atol.columns))&(y_<=2018)
def nnls(A,b,it=300):
    G=A.T@A;c=A.T@b;x=np.zeros(A.shape[1]);g=np.maximum(np.diag(G),1e-9)
    for _ in range(it):
        for j in range(len(x)): x[j]=max(0,(c[j]-G[j]@x+G[j,j]*x[j])/g[j])
    return x
Xc=X2.loc[idx]; cats=[k for k in Y.columns if k!='artif']; A=Xc.values[tr]; keep=np.where(A.sum(axis=0)>0)[0]
coef=pd.DataFrame(0.0,index=Xc.columns,columns=cats)
for k in cats: coef.loc[Xc.columns[keep],k]=nnls(A[:,keep],Yha[k].values[tr])
tab=pd.read_csv('table_natures_categories.csv').set_index('nature')
ART=['resid','comm','equip','loisirs','agri_bat','indus','carrieres','transport','autres_art']
hard={n:(tab.categorie[n] if tab.source[n]=='libelle' else coef.loc[n].idxmax()) for n in X.columns}
diff=[(n,tab.libelle[n],tab.categorie[n],hard[n],tab.ha_2023[n]) for n in X.columns if hard[n]!=tab.categorie[n]]
print('natures qui changent de categorie',len(diff)); print(diff[:15])
print('table complete: part artif identique',sum((hard[n] in ART)==(tab.categorie[n] in ART) for n in X.columns),'/',len(X.columns))
sel=[n for n in X.columns if hard[n] in ART]
sp=X[sel].sum(axis=1).unstack(0).sort_index(); fs=sp.diff().shift(-1)
yrs=[2019,2020,2021]; com=[k for k in atol.columns]
e=(fs.loc[yrs,com]-atol.loc[yrs,com]).stack()
print('ATOL 2019-2021 hors echantillon: |e| med',round(e.abs().median(),2),'moy',round(e.abs().mean(),2),'>1ha %',round((e.abs()>1).mean()*100,1),'r',round(np.corrcoef(fs.loc[yrs,com].values.ravel(),atol.loc[yrs,com].values.ravel())[0,1],4))
