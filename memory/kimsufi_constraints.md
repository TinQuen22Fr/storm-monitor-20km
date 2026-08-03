# ⛔ CONTRAINTES ABSOLUES — Serveur de production/dev de l'utilisateur

## Matériel : Kimsufi OVH — Intel ATOM D425 (2010)
CPU ancien : PAS de SSE4.1/SSE4.2, PAS d'AVX, PAS de POPCNT.
Tout binaire compilé avec des instructions modernes → `Illegal instruction (core dumped)`
et le service systemd boucle en silence (logs figés, status "running" mensonger).

## RÈGLES ABSOLUES (ordre utilisateur du 03/08/2026)
1. **JAMAIS de paquets récents nécessitant des instructions CPU modernes.**
   Toujours des versions stables, légères, wheels précompilées manylinux2014
   (baseline x86-64), AUCUNE compilation lourde depuis les sources.
2. **JAMAIS de paquets propriétaires sandbox dans requirements.txt**
   (`emergentintegrations`, `litellm`, `boto3`, etc. → introuvables sur PyPI ou inutiles).
   requirements.txt = UNIQUEMENT les deps réelles du backend, jamais un `pip freeze`.
3. **JAMAIS de Node.js récent** : le serveur tourne en Node 20 (binaire prouvé sur l'Atom).
   Vite est PINNÉ en v5 (compatible Node 18/20 sans exigence de minor).
   Ne JAMAIS remonter Vite ≥7 (exige Node 20.19+/22) ni installer Node 22 sur l'Atom.
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
