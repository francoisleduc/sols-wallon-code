import sys, zipfile, re, unicodedata, pandas as pd, numpy as np
S=sys.argv[1]; P=sys.argv[2]
def norm(s):
    s=unicodedata.normalize('NFKD',str(s)).encode('ascii','ignore').decode().upper()
    return re.sub(r'[^A-Z]','',s)
# IWEPS
cats=['artif','resid','comm','equip','loisirs','agri_bat','indus','carrieres','transport','autres_art','arable','herbe','foret','seminat','humide','eau','inconnu']
iw=[]
for i,c in enumerate(cats):
    x=pd.read_csv(f'{S}/dl_iweps/api/p{i}.csv',skiprows=1,header=None,names=['ins','type','ent','per','val'])
    x['cat']=c; x['an']=x.per.str[-4:].astype(int); iw.append(x[['ins','ent','an','cat','val']])
iw=pd.concat(iw)
print('iweps codes',iw.ins.nunique()); 
q=pd.read_csv(f'{P}/data/processed/artif_communes_stock_annuel.csv')
print('statbel codes',q.code_ins.nunique())
print('iweps hors statbel',iw[~iw.ins.isin(q.code_ins)][['ins','ent']].drop_duplicates().to_string())
print('statbel hors iweps',q[~q.code_ins.isin(iw.ins)][['code_ins','commune']].drop_duplicates().to_string())
print(iw[iw.ent.str.contains('Bastogne|Bertogne')&(iw.cat=='artif')&(iw.an.isin([2002,2023]))].to_string())
ref=q[['code_ins','commune']].drop_duplicates()
ref['k']=ref.commune.map(norm)
# SPF
fr=[]
for y in range(2011,2027):
    z=zipfile.ZipFile(f'{S}/test_spf/zips/{y}.zip')
    n=[n for n in z.namelist() if 'municipal' in n.lower() and n.lower().endswith('.csv')][0]
    with z.open(n) as h: df=pd.read_csv(h,sep=';',dtype=str,encoding='utf-8-sig')
    df=df[df.ParcelNature.str.isdigit()]
    fr.append(pd.DataFrame({'nis':df.NISCode.astype(int),'name':df.NameFre,'nat':df.ParcelNature.astype(int),'m2':pd.to_numeric(df.TotalParcelsArea),'n':pd.to_numeric(df.ParcelsNumber),'an':y}))
d=pd.concat(fr)
d=d[((d.nis>=25000)&(d.nis<30000))|((d.nis>=50000)&(d.nis<70000))|(d.nis>=80000)]
nm=d[['nis','name']].drop_duplicates(); nm['k']=nm.name.map(norm)
mp=nm.merge(ref,on='k',how='left')
print('sans correspondance',mp[mp.code_ins.isna()].to_string())
print(mp[mp.nis!=mp.code_ins].shape)
mp.to_csv(f'{S}/test_spf/map_nis.csv',index=False)
d=d.merge(mp[['nis','name','code_ins']],on=['nis','name'],how='left')
d.to_csv(f'{S}/test_spf/spf_natures.csv',index=False)
print(d.groupby('an').code_ins.nunique().to_dict(), d.code_ins.isna().sum())
iw.to_csv(f'{S}/test_spf/iweps_long.csv',index=False)
