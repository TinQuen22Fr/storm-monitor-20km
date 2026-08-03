# ⛔ CONTRAINTES ABSOLUES — Serveur de production/dev de l'utilisateur

## Matériel : Kimsufi OVH — Intel ATOM D425 (2010)
Flags CPU RÉELS (relevé utilisateur 03/08/2026) — plafond SIMD = **SSSE3** :
`fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat pse36 clflush
dts acpi mmx fxsr sse sse2 ss ht tm pbe syscall nx lm constant_tsc arch_perfmon
pebs bts nopl nonstop_tsc cpuid aperfmperf pni dtes64 monitor ds_cpl est tm2
ssse3 cx16 xtpr pdcm movbe lahf_lm dtherm arat`
→ PAS de sse4_1, PAS de sse4_2, PAS de popcnt, PAS d'avx.
Tout binaire compilé avec ces instructions → `Illegal instruction (core dumped)`
et le service systemd boucle en silence (logs figés, status "running" mensonger).
Les wheels manylinux standard visent la baseline x86-64 (SSE2) = OK, mais seul
un IMPORT RÉEL sur la machine fait foi → upgrade.sh exécute `check_cpu_binaries`
(import de chaque module binaire du venv) SYSTÉMATIQUEMENT avant tout restart.

## RÈGLES ABSOLUES (ordres utilisateur des 03/08/2026)
0. **AUCUNE intervention non sollicitée.** Le projet fonctionnait en production avant
   les mises à jour. Modifications MINIMALES, uniquement ce qui est demandé,
   zéro proposition spontanée, zéro "amélioration" non requise. L'utilisateur menace
   de résilier — chaque changement doit être justifié et prouvé.
1. **JAMAIS de paquets récents nécessitant des instructions CPU modernes.**
   Toujours des versions stables, légères, wheels précompilées manylinux2014
   (baseline x86-64), AUCUNE compilation lourde depuis les sources.
2. **JAMAIS de paquets propriétaires sandbox dans requirements.txt**
   (`emergentintegrations`, `litellm`, `boto3`, etc. → introuvables sur PyPI ou inutiles).
   requirements.txt = UNIQUEMENT les deps réelles du backend, jamais un `pip freeze`.
3. **Node.js : NE JAMAIS Y TOUCHER.** Le Kimsufi tourne en **Node v26.5.0, prouvé
   fonctionnel sur l'Atom** (info utilisateur 03/08). install.sh conserve tout node ≥18,
   aucun downgrade/upgrade forcé. Vite est pinné en v5 (compatible Node 18→26).
4. **Un test sandbox validé NE confirme PAS le fonctionnement sur le Kimsufi.**
   Toute modif risquée doit être accompagnée d'un bloc de commandes de vérification
   que l'utilisateur exécute lui-même sur son serveur (je n'ai pas d'accès SSH).
5. MongoDB : le serveur utilise une version ancienne (Mongo ≥5 exige AVX → interdit).
   Ne jamais pinner pymongo/motor au-delà des versions actuelles (pymongo 4.5, motor 3.3.1).
6. Le backend doit TOUJOURS avoir des imports défensifs (try/except ImportError)
   pour tout nouveau paquet Python.

## Versions Python verrouillées (prouvées sur l'Atom par le diagnostic user du 03/08)
Voir /app/backend/requirements.txt : pydantic 2.6.4, websockets 12.0, pillow 10.4.0,
cryptography 42.0.8, pywebpush 1.14.1, reportlab 4.2.5, httpx 0.28.1 → tous « ok »
au test d'import réel sur le serveur. firebase-admin 7.5.0 conservé (prouvé).
**SHAPELY = BANNI DÉFINITIVEMENT** : SIGILL confirmé sur le serveur (2.1.2 ET 2.0.7,
GEOS compilé SSE4). Remplacé le 03/08 par du Python pur dans geo.py (ray casting +
adjacence pré-calculée dans data/departements-adjacence.json). Ne JAMAIS réintroduire
shapely ni aucune lib géométrique binaire (GEOS/GDAL/pyproj/rtree).

## Diagnostic SIGILL sur le serveur
```
cd /var/www/storm-monitor/backend
for m in pydantic fastapi motor shapely PIL reportlab firebase_admin websockets httpx bcrypt jwt cryptography; do
  venv/bin/python -c "import $m" >/dev/null 2>&1; rc=$?
  [ $rc -eq 132 ] && echo "$m -> ILLEGAL INSTRUCTION" || echo "$m -> ok($rc)"
done
```
