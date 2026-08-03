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

## RÈGLES ABSOLUES (ordre utilisateur du 03/08/2026)
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

## Versions Python verrouillées (prouvées génération Atom, wheels manylinux2014)
Voir /app/backend/requirements.txt : pydantic 2.6.4, websockets 12.0, pillow 10.4.0,
shapely 2.0.7, cryptography 42.0.8, pywebpush 1.14.1, reportlab 4.2.5, httpx 0.27.2.
firebase-admin 7.5.0 conservé (installé et prouvé par l'utilisateur en juin 2026).

## Diagnostic SIGILL sur le serveur
```
cd /var/www/storm-monitor/backend
for m in pydantic fastapi motor shapely PIL reportlab firebase_admin websockets httpx bcrypt jwt cryptography; do
  venv/bin/python -c "import $m" >/dev/null 2>&1; rc=$?
  [ $rc -eq 132 ] && echo "$m -> ILLEGAL INSTRUCTION" || echo "$m -> ok($rc)"
done
```
