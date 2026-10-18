"""Só lista o conteúdo dos zips (não extrai)."""
import sys, zipfile
from collections import Counter
from pathlib import PurePosixPath

sys.stdout.reconfigure(encoding="utf-8")

for caminho in sys.argv[1:]:
    z = zipfile.ZipFile(caminho)
    infos = [i for i in z.infolist() if not i.is_dir()]
    ext = Counter(PurePosixPath(i.filename).suffix.lower() for i in infos)
    pastas = Counter(str(PurePosixPath(i.filename).parent) for i in infos)
    tam = sorted(i.file_size for i in infos)
    print(f"\n=== {caminho}")
    print(f"arquivos: {len(infos)} | total descompactado: {sum(tam)/1e6:.1f} MB")
    print("extensões:", ext.most_common(10))
    print("pastas:", pastas.most_common(8))
    if tam:
        print(f"tamanho por arquivo: min {tam[0]/1e3:.1f} KB | mediana {tam[len(tam)//2]/1e3:.1f} KB | max {tam[-1]/1e6:.2f} MB")
    for i in infos[:12]:
        print(f"   {i.file_size/1e3:9.1f} KB  {i.filename}")
