"""Package validation for a protected account-storage credential."""
from common import u,string

def cook(p):
    if not isinstance(p,dict)or set(p)!={'minimum','maximum','comparison','alphabet','forbidden'}:raise ValueError('storage credential vocabulary')
    lo,hi=p['minimum'],p['maximum'];alphabet=p['alphabet'];words=p['forbidden']
    if type(lo)is not int or type(hi)is not int or not 1<=lo<=hi<=128:raise ValueError('storage credential lengths')
    if not isinstance(alphabet,str)or not 1<=len(alphabet)<=94 or any(not 33<=ord(c)<=126 for c in alphabet)or list(alphabet)!=sorted(set(alphabet)):raise ValueError('storage credential alphabet')
    if not isinstance(words,list)or len(words)>400:raise ValueError('storage credential forbidden count')
    if p['comparison'] not in ('exact','ascii-insensitive'):raise ValueError('storage credential comparison')
    out=b'N3K1'+u(lo)+u(hi)+u(int(p['comparison']=='ascii-insensitive'))+string(alphabet)+u(len(words));seen=set()
    for word in words:
        if not isinstance(word,str)or not 1<=len(word)<=64 or any(not 32<=ord(c)<=126 for c in word)or word.upper()in seen:raise ValueError('storage credential forbidden word')
        word=word.upper();seen.add(word);out+=string(word)
    return out
