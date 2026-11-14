import re,sys,json
t=open(sys.argv[1],encoding='utf-8').read().split('\n')
start=[i for i,l in enumerate(t) if 'Valeurs de l' in l and 'attribut' in l]
print(start[:5])
i0=next(i for i,l in enumerate(t) if l.strip()=='Terre agricole')-1
lab={}
i=i0
end=next(i for i,l in enumerate(t) if l.strip()=='I' and i>i0)
prev=-1
while i<end:
    l=t[i].strip()
    if re.fullmatch(r'\d{1,3}',l) and int(l)>prev:
        j=i+1; name=[]
        while j<end and not re.match(r'(Toute|Parcelle|Nature suppl|Tout |Partie|Ensemble|Immeuble|Bien|Droit|Construction)',t[j].strip()) and len(name)<4:
            if t[j].strip(): name.append(t[j].strip())
            j+=1
        lab[int(l)]=' '.join(name); prev=int(l)
    i+=1
print(len(lab))
json.dump(lab,open(sys.argv[2],'w',encoding='utf-8'),ensure_ascii=False,indent=0)
