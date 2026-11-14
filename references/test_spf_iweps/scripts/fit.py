import sys,re,json,pandas as pd,numpy as np
S=sys.argv[1]; P=sys.argv[2]
d=pd.read_csv(f'{S}/test_spf/spf_natures.csv')
d.loc[d.name=='Bertogne','code_ins']=82039
d['code_ins']=d.code_ins.astype(int)
X=d.pivot_table(index=['code_ins','an'],columns='nat',values='m2',aggfunc='sum',fill_value=0)/1e4
q=pd.read_csv(f'{P}/data/processed/artif_communes_stock_annuel.csv').rename(columns={'annee_stock_1er_janvier':'an'})
sup=q.set_index(['code_ins','an']).superficie_ha
print('surface statbel 2024/25', q[q.an==2025].superficie_ha.sum())
# etendre superficie 2026 par 2025
a26=sup.xs(2025,level='an').to_frame('s'); a26['an']=2026; a26=a26.reset_index().set_index(['code_ins','an']).s
sup=pd.concat([sup,a26])
X['noncad']=(sup.reindex(X.index)-X.sum(axis=1)).clip(lower=0)
print('noncad median %',(X['noncad']/sup.reindex(X.index)).median()*100)
iw=pd.read_csv(f'{S}/test_spf/iweps_long.csv'); iw=iw[~iw.ins.isin([82003,82005])]
Y=iw.pivot_table(index=['ins','an'],columns='cat',values='val'); Y.index.names=['code_ins','an']
idx=X.index.intersection(Y.index)
print(len(idx), idx.get_level_values(1).min(), idx.get_level_values(1).max())
Yha=Y.loc[idx].mul(sup.reindex(idx),axis=0)/100
Xc=X.loc[idx]
def nnls(A,b,it=400):
    G=A.T@A; c=A.T@b; x=np.zeros(A.shape[1]); dg=np.maximum(np.diag(G),1e-9)
    for _ in range(it):
        for j in range(len(x)):
            r=c[j]-G[j]@x+G[j,j]*x[j]
            x[j]=max(0,r/dg[j])
    return x
rng=np.random.RandomState(42)
comm=np.array(sorted(set(idx.get_level_values(0))))
rng.shuffle(comm); test=set(comm[:len(comm)//3])
c=idx.get_level_values(0); yr=idx.get_level_values(1)
tr=(~c.isin(test))&(yr<=2018); te=(c.isin(test))&(yr>=2019)
cats=[k for k in Y.columns if k!='artif']
A=Xc.values
keep=np.where(A[tr].sum(axis=0)>0)[0]
coef=pd.DataFrame(0.0,index=Xc.columns,columns=cats)
for k in cats:
    coef.loc[Xc.columns[keep],k]=nnls(A[tr][:,keep],Yha[k].values[tr])
coef.to_csv(f'{S}/test_spf/coef.csv')
assign=coef.idxmax(axis=1); top=coef.max(axis=1)
pd.DataFrame({'cat':assign,'coef':top,'somme':coef.sum(axis=1)}).to_csv(f'{S}/test_spf/assign_auto.csv')
artc=['resid','comm','equip','loisirs','agri_bat','indus','carrieres','transport','autres_art']
pred=pd.DataFrame(A@coef.values,index=idx,columns=cats)
s=sup.reindex(idx)
for name,m in [('train',tr),('test',te)]:
    err=((pred[artc].sum(axis=1)-Yha['artif'])/s*100)[m]
    print(name,'artif: MAE points',err.abs().mean().round(3),'median',err.abs().median().round(3),'biais',err.mean().round(3))
    print({k:round(((pred[k]-Yha[k])/s*100)[m].abs().mean(),2) for k in cats})
