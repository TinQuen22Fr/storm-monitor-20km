#!/usr/bin/env bash
#
# Storm Monitor — UPGRADE script (mise à jour rapide, sans réinstall système)
# Usage:  bash upgrade.sh
#
# Note Kimsufi/OVH : la machine est déjà root par défaut — pas de `sudo` requis.
#
# Différence avec install.sh :
#   - install.sh = installation complète (nginx, mongo, node, systemd, certbot…)
#   - upgrade.sh = juste le code et les deps applicatives (rapide, ~30 s à 2 min)
#
# Ce que fait upgrade.sh :
#   1. git pull dans /opt/storm-monitor (branche Version_With_Detector figée)
#   2. Détecte ce qui a changé (requirements.txt, package.json, frontend, backend)
#   3. Backup auto du .env
#   4. rsync /opt → /var/www (en préservant runtime : .env, venv, build, cache, json)
#   5. pip install      ← SEULEMENT si requirements.txt a bougé
#   6. yarn install     ← SEULEMENT si package.json ou yarn.lock a bougé
#   7. yarn build       ← SEULEMENT si frontend/ a bougé
#   8. systemctl restart storm-monitor (toujours)
#   9. nginx reload     ← seulement si vhost/snippet a bougé
#
# Ce que upgrade.sh NE fait PAS (utiliser install.sh pour ça) :
#   - Installer apt packages (Python, Node, MongoDB, Nginx, ffmpeg, snap…)
#   - Régénérer vhost Nginx ou unit systemd
#   - Toucher au .env (juste backup)
#   - Configurer certbot ou la pile HTTPS/HTTP3

set -euo pipefail

# Flag optionnel : bash upgrade.sh --with-deps
#   Sans ce flag, le venv Python n'est JAMAIS touché (pas de pip install),
#   même si requirements.txt a changé. Le script se contente de le signaler.
WITH_DEPS=0
for arg in "$@"; do
  [[ "$arg" == "--with-deps" ]] && WITH_DEPS=1
done

REPO_URL="https://github.com/TinQuen22Fr/storm-monitor-20km.git"
# Branche cible FIGÉE — Version_With_Detector est la seule branche prod du Kimsufi.
BRANCH="Version_With_Detector"
WORK_DIR="/opt/storm-monitor"
APP_DIR="/var/www/storm-monitor"
RUN_USER="root"

# ---------------------------------------------------------------------------
# 0. Pre-flight
# ---------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
  echo "ERROR: privilèges root requis." >&2
  echo "       Kimsufi (root direct) : bash upgrade.sh" >&2
  echo "       Dedibox (compte quentin) : sudo bash upgrade.sh" >&2
  exit 1
fi

if [[ ! -d "$WORK_DIR/.git" ]]; then
  echo "ERROR: $WORK_DIR n'est pas un clone git." >&2
  echo "       Première installation requise : lance d'abord 'bash install.sh'." >&2
  exit 1
fi

# Dedibox : si le clone /opt a été fait par un utilisateur (ex: quentin) et que
# le script tourne en sudo/root, git refuse d'opérer ("dubious ownership").
# On déclare le dépôt sûr pour root — idempotent.
if ! git config --global --get-all safe.directory 2>/dev/null | grep -qx "$WORK_DIR"; then
  git config --global --add safe.directory "$WORK_DIR"
fi

if [[ ! -d "$APP_DIR/backend" || ! -d "$APP_DIR/frontend" ]]; then
  echo "ERROR: $APP_DIR ne contient pas backend/ et frontend/." >&2
  echo "       Première installation requise : lance d'abord 'bash install.sh'." >&2
  exit 1
fi

START_TS=$(date +%s)
CPU_MODEL="$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2- | xargs || echo inconnu)"
CPU_FLAGS="$(grep -m1 '^flags' /proc/cpuinfo 2>/dev/null || true)"
# Niveau SIMD réellement supporté par CE processeur (aucune supposition) :
# Atom D425 = plafond SSSE3 → tout binaire compilé SSE4.x/AVX meurt en SIGILL.
CPU_SIMD="sse2"
echo "$CPU_FLAGS" | grep -qw ssse3  && CPU_SIMD="ssse3"
echo "$CPU_FLAGS" | grep -qw sse4_2 && CPU_SIMD="sse4_2"
echo "$CPU_FLAGS" | grep -qw avx    && CPU_SIMD="avx"
CPU_OLD=0
if ! echo "$CPU_FLAGS" | grep -qw sse4_2; then
  CPU_OLD=1
fi
echo "==> Storm Monitor — UPGRADE rapide sur $(hostname)"
echo "    Work dir : $WORK_DIR"
echo "    App dir  : $APP_DIR"
echo "    Branch   : $BRANCH"
echo "    CPU      : $CPU_MODEL — plafond SIMD réel : $CPU_SIMD"
if [[ $CPU_OLD -eq 1 ]]; then
  echo "    MODE CPU ANCIEN : pas de SSE4.x/AVX — chaque module binaire sera testé"
  echo "    par import réel sur CE processeur avant tout redémarrage du service."
fi

# ---------------------------------------------------------------------------
# Contrôle CPU : importe chaque module binaire avec le python du venv déployé.
# rc=132 = Illegal instruction = paquet compilé avec des instructions absentes
# de ce processeur. Appelé APRÈS pip et AVANT tout restart — on ne tue jamais
# un service qui tourne pour le remplacer par un binaire qui crashe.
# ---------------------------------------------------------------------------
check_cpu_binaries() {
  local venv_py="$APP_DIR/backend/venv/bin/python"
  if [[ ! -x "$venv_py" ]]; then
    echo "    WARN: venv absent — contrôle CPU des modules sauté"
    return 0
  fi
  echo "    Contrôle CPU : import réel de chaque module binaire ($CPU_MODEL)..."
  local fail=0 m rc
  # numpy : non requis par le projet, mais s'il traîne dans le venv (reliquat)
  # et qu'il est incompatible CPU, tout module qui l'importe opportunément meurt.
  for m in pydantic fastapi motor pymongo numpy PIL reportlab firebase_admin websockets httpx bcrypt jwt cryptography; do
    set +e
    "$venv_py" -c "import $m" >/dev/null 2>&1
    rc=$?
    set -e
    if [[ $rc -eq 132 || $rc -eq 139 ]]; then
      echo "ERROR: module Python '$m' → Illegal instruction/segfault sur ce CPU." >&2
      fail=1
    elif [[ $rc -ne 0 ]]; then
      echo "    (module $m absent ou erreur d'import bénigne, rc=$rc — toléré)"
    fi
  done
  if [[ $fail -eq 1 ]]; then
    echo "ERROR: paquet(s) incompatible(s) avec ce processeur — pinner une version" >&2
    echo "       plus ancienne (ou désinstaller le reliquat : venv/bin/pip uninstall <paquet>)." >&2
    echo "       UPGRADE BLOQUÉ — le service N'A PAS été redémarré." >&2
    exit 1
  fi
  # GARANTIE FINALE : import de la chaîne COMPLÈTE de l'application (server.py
  # tire reports, weather, geo, push, fcm… exactement comme uvicorn au boot).
  # C'est le seul test qui attrape TOUT — y compris un import opportuniste
  # d'un reliquat du venv (cas vécu : reports → numpy 2.4.4 → SIGILL).
  echo "    Test d'import COMPLET de l'application (chaîne réelle de server.py)..."
  local out rc2
  set +e
  out="$(cd "$APP_DIR/backend" && timeout 180 venv/bin/python -c 'import server' 2>&1)"
  rc2=$?
  set -e
  if [[ $rc2 -eq 0 ]]; then
    echo "    ✓ 'import server' passe — chaîne complète compatible avec ce CPU"
  else
    if [[ $rc2 -eq 132 || $rc2 -eq 139 || "$out" == *"Illegal instruction"* ]]; then
      echo "ERROR: 'import server' meurt en Illegal instruction sur ce CPU." >&2
    else
      echo "ERROR: 'import server' échoue (rc=$rc2) :" >&2
    fi
    echo "$out" | tail -n 15 >&2
    echo "ERROR: UPGRADE BLOQUÉ — le service N'A PAS été redémarré (l'ancien process reste en place)." >&2
    exit 1
  fi
  echo "    ✓ Tous les contrôles CPU passent réellement sur cette machine"
}

# ---------------------------------------------------------------------------
# 1. Git pull dans WORK_DIR (avec stash auto si modifs locales)
# ---------------------------------------------------------------------------
echo ""
echo "==> Étape 1 — Mise à jour du clone Git ($WORK_DIR)..."

CURRENT_BRANCH="$(git -C "$WORK_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"
OLD_COMMIT="$(git -C "$WORK_DIR" rev-parse HEAD 2>/dev/null || echo 'unknown')"

# Discard les fichiers runtime jamais trackés
rm -f "$WORK_DIR/backend/.stale_cache.pkl"

STASH_CREATED=0
if ! git -C "$WORK_DIR" diff --quiet || ! git -C "$WORK_DIR" diff --cached --quiet; then
  echo "    Modifs locales détectées — stash automatique..."
  if git -C "$WORK_DIR" -c user.name="upgrade.sh" -c user.email="upgrade@storm-monitor.local" stash push -u -m "upgrade.sh auto-stash $(date -u +%FT%TZ)" >/dev/null 2>&1; then
    STASH_CREATED=1
  fi
fi

git -C "$WORK_DIR" remote set-url origin "$REPO_URL"
git -C "$WORK_DIR" fetch --prune origin

# Auto-heal : si un run précédent a laissé des conflits git (stash pop raté),
# on repart proprement de la branche distante. Les fichiers runtime (.env,
# proxies.json, storm_data.json…) ne sont pas trackés → intacts.
if [[ -n "$(git -C "$WORK_DIR" ls-files -u 2>/dev/null)" ]]; then
  echo "    Conflits git résiduels détectés — reset hard sur origin/$BRANCH"
  git -C "$WORK_DIR" reset --hard "origin/$BRANCH"
  git -C "$WORK_DIR" stash drop >/dev/null 2>&1 || true
  STASH_CREATED=0
fi

if [[ "$CURRENT_BRANCH" != "$BRANCH" ]]; then
  echo "    Switch de branche : $CURRENT_BRANCH → $BRANCH"
  git -C "$WORK_DIR" checkout -B "$BRANCH" "origin/$BRANCH"
else
  if ! git -C "$WORK_DIR" pull --ff-only origin "$BRANCH"; then
    echo "    Fast-forward impossible — reset hard sur origin/$BRANCH"
    git -C "$WORK_DIR" reset --hard "origin/$BRANCH"
  fi
fi

NEW_COMMIT="$(git -C "$WORK_DIR" rev-parse HEAD)"

if [[ $STASH_CREATED -eq 1 ]]; then
  if ! git -C "$WORK_DIR" stash pop >/dev/null 2>&1; then
    # Un pop en conflit laisse des marqueurs <<<<<<< dans les fichiers → pip
    # et yarn plantent. On abandonne les modifs locales : la vérité = le dépôt.
    echo "    WARN: conflits au stash pop — abandon des modifs locales (reset origin/$BRANCH)"
    git -C "$WORK_DIR" reset --hard "origin/$BRANCH"
    git -C "$WORK_DIR" stash drop >/dev/null 2>&1 || true
  fi
fi

# Si upgrade.sh lui-même a changé dans ce pull, on RELANCE immédiatement la
# nouvelle version : bash lit le script au fil de l'exécution, continuer avec
# l'ancienne version en mémoire après un pull = comportement imprévisible
# (c'est pour ça que les correctifs du script ne prenaient effet qu'au run suivant).
if [[ "${STORM_UPGRADE_REEXEC:-0}" != "1" && "$OLD_COMMIT" != "$NEW_COMMIT" ]]; then
  if git -C "$WORK_DIR" diff --name-only "$OLD_COMMIT" "$NEW_COMMIT" 2>/dev/null | grep -qx 'upgrade.sh'; then
    echo "    upgrade.sh mis à jour dans ce pull — relance avec la NOUVELLE version..."
    exec env STORM_UPGRADE_REEXEC=1 STORM_UPGRADE_BASE="$OLD_COMMIT" bash "$WORK_DIR/upgrade.sh" "$@"
  fi
fi

# Les fichiers de dépendances doivent TOUJOURS être ceux du dépôt : une modif
# locale (npm install parasite, merge raté…) casse `yarn --frozen-lockfile`
# et fausse la détection pip. On les restaure d'office après le stash pop.
# `checkout HEAD --` fonctionne même sur un fichier en état de conflit.
git -C "$WORK_DIR" checkout HEAD -- frontend/yarn.lock frontend/package.json backend/requirements.txt 2>/dev/null || true
rm -f "$WORK_DIR/package-lock.json"   # artefact npm à la racine, jamais légitime ici

# Ceinture + bretelles : aucun marqueur de conflit ne doit subsister dans les
# fichiers de deps, sinon pip/yarn exploseront plus loin.
if grep -qE '^(<<<<<<<|=======|>>>>>>>)' "$WORK_DIR/backend/requirements.txt" "$WORK_DIR/frontend/package.json" 2>/dev/null; then
  echo "ERROR: marqueurs de conflit git dans requirements.txt/package.json." >&2
  echo "       Répare avec : git -C $WORK_DIR reset --hard origin/$BRANCH  puis relance." >&2
  exit 1
fi

if [[ "$OLD_COMMIT" == "$NEW_COMMIT" ]]; then
  echo "    ✓ Déjà à jour sur $(git -C "$WORK_DIR" rev-parse --short HEAD) — rien à puller"
  ALREADY_UP_TO_DATE=1
else
  echo "    ✓ ${OLD_COMMIT:0:7} → ${NEW_COMMIT:0:7}"
  git -C "$WORK_DIR" log --pretty=format:'      - %h %s' "$OLD_COMMIT..$NEW_COMMIT" 2>/dev/null | head -15 || true
  echo ""
  ALREADY_UP_TO_DATE=0
fi

# ---------------------------------------------------------------------------
# 2. Détection des changements (par dossier/fichier)
# ---------------------------------------------------------------------------
# Si pas de nouveaux commits, on peut sauter pip/yarn/build mais on resync
# quand même (au cas où des fichiers de /var/www auraient été touchés à la main).
echo ""
echo "==> Étape 2 — Détection des changements..."

# Après un re-exec (upgrade.sh auto-mis à jour), la base de comparaison est le
# commit d'AVANT le pull du premier passage, sinon tout serait vu "inchangé".
if [[ -n "${STORM_UPGRADE_BASE:-}" ]]; then
  OLD_COMMIT="$STORM_UPGRADE_BASE"
  ALREADY_UP_TO_DATE=0
fi

REQ_CHANGED=0
PKG_CHANGED=0
FRONTEND_CHANGED=0
BACKEND_CHANGED=0
NGINX_CHANGED=0

if [[ $ALREADY_UP_TO_DATE -eq 0 ]]; then
  CHANGED_FILES="$(git -C "$WORK_DIR" diff --name-only "$OLD_COMMIT" "$NEW_COMMIT" 2>/dev/null || true)"
  if echo "$CHANGED_FILES" | grep -qE '^backend/requirements\.txt$'; then REQ_CHANGED=1; fi
  if echo "$CHANGED_FILES" | grep -qE '^frontend/(package\.json|yarn\.lock)$'; then PKG_CHANGED=1; fi
  if echo "$CHANGED_FILES" | grep -qE '^frontend/'; then FRONTEND_CHANGED=1; fi
  if echo "$CHANGED_FILES" | grep -qE '^backend/'; then BACKEND_CHANGED=1; fi
  if echo "$CHANGED_FILES" | grep -qE '^(install\.sh|.*nginx.*\.conf|.*systemd.*\.service)$'; then NGINX_CHANGED=1; fi
fi

# Le venv est PROTÉGÉ : jamais recréé, jamais modifié sans --with-deps explicite.
if [[ ! -d "$APP_DIR/backend/venv" ]]; then
  echo "    WARN: venv absent ($APP_DIR/backend/venv) — lance 'bash upgrade.sh --with-deps' pour le créer"
fi
# Contrôle informatif seulement (aucune action automatique sur le venv)
if [[ -x "$APP_DIR/backend/venv/bin/python" ]]; then
  if ! "$APP_DIR/backend/venv/bin/python" -c "import firebase_admin" 2>/dev/null; then
    echo "    WARN: module firebase_admin absent du venv — installe-le manuellement ou lance '--with-deps'"
  fi
fi
# Force le rebuild si le build déployé ne correspond pas au dernier commit ayant
# touché frontend/ (protège contre un run précédent planté APRÈS le git pull :
# le code est à jour dans /opt mais le build de /var/www est resté ancien,
# et « Déjà à jour » sautait silencieusement le yarn build).
FRONTEND_COMMIT="$(git -C "$WORK_DIR" log -1 --format=%H -- frontend/ 2>/dev/null || echo unknown)"
BUILD_STAMP="$APP_DIR/frontend/build/.build-commit"
if [[ ! -f "$BUILD_STAMP" || "$(cat "$BUILD_STAMP" 2>/dev/null)" != "$FRONTEND_COMMIT" ]]; then
  echo "    build frontend absent ou issu d'un ancien commit — rebuild forcé"
  FRONTEND_CHANGED=1
fi
# Si le build n'existe pas, on force aussi
if [[ ! -d "$APP_DIR/frontend/build" ]]; then
  FRONTEND_CHANGED=1
  PKG_CHANGED=1
fi
# Si node_modules est absent ou périmé (deps déclarées mais pas installées,
# ex: @capacitor/core), on force yarn install
if [[ ! -d "$APP_DIR/frontend/node_modules" ]]; then
  PKG_CHANGED=1
else
  while IFS= read -r dep; do
    if [[ ! -d "$APP_DIR/frontend/node_modules/$dep" ]]; then
      echo "    dépendance '$dep' absente de node_modules — yarn install forcé"
      PKG_CHANGED=1
      break
    fi
  done < <(python3 -c "import json;print('\n'.join(json.load(open('$WORK_DIR/frontend/package.json'))['dependencies'].keys()))" 2>/dev/null)
fi

echo "    requirements.txt : $([[ $REQ_CHANGED -eq 1 ]] && echo 'CHANGÉ' || echo 'inchangé')"
echo "    package.json/lock: $([[ $PKG_CHANGED -eq 1 ]] && echo 'CHANGÉ' || echo 'inchangé')"
echo "    frontend/        : $([[ $FRONTEND_CHANGED -eq 1 ]] && echo 'CHANGÉ' || echo 'inchangé')"
echo "    backend/         : $([[ $BACKEND_CHANGED -eq 1 ]] && echo 'CHANGÉ' || echo 'inchangé')"

# ---------------------------------------------------------------------------
# 3. Backup du .env
# ---------------------------------------------------------------------------
ENV_FILE="$APP_DIR/backend/.env"
if [[ -f "$ENV_FILE" ]]; then
  BACKUP_DIR="$APP_DIR/backend/.env.backups"
  mkdir -p "$BACKUP_DIR"
  BACKUP_FILE="$BACKUP_DIR/.env.$(date -u +%Y%m%dT%H%M%SZ)"
  # cp SANS -a : le mtime du backup = maintenant (pas celui, ancien, du .env
  # source). Avec -a, le backup héritait d'un mtime vieux de plusieurs semaines :
  # invisible dans `ls -lt` et supprimable par la rotation triée par date.
  cp "$ENV_FILE" "$BACKUP_FILE"
  chmod 600 "$BACKUP_FILE"
  if [[ ! -s "$BACKUP_FILE" ]]; then
    echo "ERROR: backup .env échoué ($BACKUP_FILE absent ou vide)" >&2
    exit 1
  fi
  echo ""
  echo "==> Étape 3 — Backup .env → $BACKUP_FILE"
  ls -l "$BACKUP_FILE"
  # Rotation FIFO 10 derniers — tri par NOM (l'horodatage est dans le nom,
  # donc l'ordre lexical = l'ordre chronologique, indépendant des mtimes)
  ROTATED=$(ls -1 "$BACKUP_DIR"/.env.* 2>/dev/null | sort -r | tail -n +11 || true)
  if [[ -n "$ROTATED" ]]; then
    echo "$ROTATED" | xargs -r rm -f
    echo "    Rotation : $(echo "$ROTATED" | wc -l) ancien(s) backup(s) supprimé(s)"
  fi
  echo "    Backups présents : $(ls -1 "$BACKUP_DIR"/.env.* 2>/dev/null | wc -l)"
fi

# ---------------------------------------------------------------------------
# 4. rsync WORK_DIR → APP_DIR (en préservant les runtime files)
# ---------------------------------------------------------------------------
echo ""
echo "==> Étape 4 — Sync $WORK_DIR → $APP_DIR..."
command -v rsync >/dev/null || { echo "ERROR: rsync absent. Lance 'apt install rsync'." >&2; exit 1; }

rsync -a --delete \
  --exclude='.git' \
  --exclude='backend/.env' \
  --exclude='backend/.env.backups' \
  --exclude='backend/venv' \
  --exclude='backend/storm_data.json' \
  --exclude='backend/firebase-admin.json' \
  --exclude='backend/.stale_cache.pkl' \
  --exclude='backend/cache' \
  --exclude='backend/__pycache__' \
  --exclude='backend/**/__pycache__' \
  --exclude='frontend/build' \
  --exclude='frontend/node_modules' \
  --exclude='frontend/.env' \
  --exclude='cache' \
  "$WORK_DIR/" "$APP_DIR/"
chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR"

# Ensure the bulk forecast cache dir exists and is writable by the service
# user. The upstream rsync excludes `cache/` (we never want to overwrite a
# user's runtime data), so we create it explicitly here if missing.
mkdir -p "$APP_DIR/backend/cache"
chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR/backend/cache"
chmod 755 "$APP_DIR/backend/cache"

# Reset le frontend/.env (URL backend prod)
cat > "$APP_DIR/frontend/.env" <<EOF
REACT_APP_BACKEND_URL=https://storm-monitor.quentin-astro.fr
EOF

# ---------------------------------------------------------------------------
# 5. Backend deps (pip install) — seulement si requirements changé
# ---------------------------------------------------------------------------
if [[ $WITH_DEPS -eq 1 ]]; then
  echo ""
  echo "==> Étape 5 — Deps Python (--with-deps : pip TOUJOURS exécuté, même si"
  echo "    requirements.txt semble inchangé — c'est la seule façon de garantir"
  echo "    que le venv correspond EXACTEMENT aux versions pinnées)..."
  cd "$APP_DIR/backend"
  if [[ ! -d venv ]]; then
    # Le venv DOIT être en Python 3.11/3.12 (les pins n'ont pas de wheels >= 3.13).
    PY_FOR_VENV=""
    for cand in python3.12 python3.11 python3; do
      if command -v "$cand" >/dev/null 2>&1; then
        v="$("$cand" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo 0)"
        case "$v" in 3.11|3.12) PY_FOR_VENV="$cand"; break ;; esac
      fi
    done
    if [[ -z "$PY_FOR_VENV" ]]; then
      echo "ERROR: aucun Python 3.11/3.12 pour créer le venv — lance 'bash install.sh' (il gère l'installation)." >&2
      exit 1
    fi
    "$PY_FOR_VENV" -m venv venv
  fi
  # shellcheck disable=SC1091
  source venv/bin/activate
  pip install --upgrade pip wheel setuptools >/dev/null
  # --prefer-binary : toujours des wheels précompilées, jamais de compilation
  # lourde depuis les sources sur l'Atom.
  pip install --prefer-binary -r requirements.txt
  deactivate
  cd - >/dev/null
elif [[ $REQ_CHANGED -eq 1 ]]; then
  echo ""
  echo "==> Étape 5 — requirements.txt a CHANGÉ mais venv protégé (pip NON exécuté)."
  echo "    Pour installer les nouvelles deps : bash upgrade.sh --with-deps"
  echo "    ou manuellement : $APP_DIR/backend/venv/bin/pip install -r $APP_DIR/backend/requirements.txt"
else
  echo ""
  echo "==> Étape 5 — pip skip (requirements.txt inchangé)"
fi

# ---------------------------------------------------------------------------
# 6. Frontend deps (yarn install) — seulement si package.json/yarn.lock changé
# ---------------------------------------------------------------------------
# Garde-fou : Vite 5 exige Node >= 18. NE PAS installer Node 22 sur l'Atom D425
# (risque "Illegal instruction") — Node 20 du serveur est la référence.
NODE_V="$(node -v 2>/dev/null || echo v0.0.0)"
NODE_MAJOR="${NODE_V#v}"; NODE_MAJOR="${NODE_MAJOR%%.*}"
if (( NODE_MAJOR < 18 )); then
  echo "ERROR: Node $NODE_V trop ancien (requis : >= 18, Node 20 recommandé)." >&2
  echo "       curl -fsSL https://deb.nodesource.com/setup_20.x | bash -" >&2
  echo "       apt-get install -y nodejs" >&2
  echo "       puis relance : bash upgrade.sh" >&2
  exit 1
fi

cd "$APP_DIR/frontend"
if [[ $PKG_CHANGED -eq 1 ]]; then
  echo ""
  echo "==> Étape 6 — Mise à jour des deps frontend (package.json changé)..."
  YARN_LOG="/var/log/storm-monitor-yarn-install.log"
  : > "$YARN_LOG"
  set +e
  yarn install --frozen-lockfile --network-timeout 600000 2>&1 | tee "$YARN_LOG" | grep -vE '^warning |^$'
  YARN_RC=${PIPESTATUS[0]}
  if [[ $YARN_RC -ne 0 ]]; then
    echo "    WARN: --frozen-lockfile a échoué (rc=$YARN_RC) — nouvel essai en mode normal..."
    yarn install --network-timeout 600000 2>&1 | tee -a "$YARN_LOG" | grep -vE '^warning |^$'
    YARN_RC=${PIPESTATUS[0]}
  fi
  set -e
  if [[ $YARN_RC -ne 0 ]]; then
    echo "ERROR: yarn install failed (rc=$YARN_RC). Voir $YARN_LOG." >&2
    exit $YARN_RC
  fi
  WARN_COUNT=$(grep -cE '^warning ' "$YARN_LOG" 2>/dev/null || true)
  WARN_COUNT=${WARN_COUNT:-0}
  echo "    [yarn] ${WARN_COUNT} warnings cosmétiques filtrés — log: $YARN_LOG"
else
  echo ""
  echo "==> Étape 6 — yarn install skip (package.json/yarn.lock inchangés)"
fi

# ---------------------------------------------------------------------------
# 7. Frontend build — seulement si frontend a bougé
# ---------------------------------------------------------------------------
if [[ $FRONTEND_CHANGED -eq 1 ]]; then
  echo ""
  echo "==> Étape 7 — Build du frontend (RAM plafonnée pour éviter l'OOM Killer)..."
  # Build dans un dossier temporaire puis swap atomique : si le build plante,
  # l'ancien build/ reste intact → le site ne devient JAMAIS blanc.
  rm -rf build.new
  NODE_OPTIONS="--max-old-space-size=1024" GENERATE_SOURCEMAP=false \
    yarn build --outDir build.new --emptyOutDir
  if [[ ! -f build.new/index.html ]]; then
    echo "ERROR: build.new/index.html absent — build incomplet, ancien build conservé." >&2
    rm -rf build.new
    exit 1
  fi
  # Empreinte du build : permet aux runs suivants de détecter un build périmé
  echo "$FRONTEND_COMMIT" > build.new/.build-commit
  rm -rf build.old
  [[ -d build ]] && mv build build.old
  mv build.new build
  rm -rf build.old
else
  echo ""
  echo "==> Étape 7 — yarn build skip (aucun fichier frontend modifié)"
fi
cd - >/dev/null

# ---------------------------------------------------------------------------
# 8. Restart backend (toujours, c'est rapide et garantit que la nouvelle conf
#    .env / les nouveaux modules Python sont chargés)
# ---------------------------------------------------------------------------
echo ""
echo "==> Étape 8 — Restart du service backend..."
# Contrôle CPU SYSTÉMATIQUE (avec ou sans --with-deps) : on ne redémarre le
# service QUE si tous les modules binaires passent sur ce processeur.
check_cpu_binaries
systemctl restart storm-monitor.service
sleep 2
if systemctl is-active --quiet storm-monitor.service; then
  echo "    ✓ storm-monitor.service est actif (systemd)"
else
  echo "ERROR: storm-monitor.service n'a pas redémarré correctement." >&2
  systemctl status storm-monitor.service --no-pager -n 20 || true
  exit 1
fi

# Sonde santé RÉELLE : systemd peut dire "active" alors que le process boucle
# en crash silencieux (ex: Illegal instruction). On exige une vraie réponse HTTP.
SVC_PORT="$(grep -oP -- '--port \K[0-9]+' /etc/systemd/system/storm-monitor.service 2>/dev/null | head -1)"
SVC_PORT="${SVC_PORT:-8001}"
echo "    Sonde santé : attente d'une réponse de l'API (127.0.0.1:$SVC_PORT/api/health)..."
HEALTH_OK=0
for _ in $(seq 1 12); do
  sleep 2
  if curl -fsS -m 4 "http://127.0.0.1:${SVC_PORT}/api/health" >/dev/null 2>&1; then
    HEALTH_OK=1
    break
  fi
done
if [[ $HEALTH_OK -eq 1 ]]; then
  echo "    ✓ Le backend répond RÉELLEMENT sur /api/health"
else
  echo "ERROR: le backend ne répond PAS sur /api/health après 24 s (systemd 'active' ne suffit pas)." >&2
  echo "       Dernières lignes de /var/log/storm-monitor.err.log :" >&2
  tail -n 25 /var/log/storm-monitor.err.log >&2 || true
  exit 1
fi

# ---------------------------------------------------------------------------
# 9. Nginx reload — seulement si vhost/snippet a bougé (rare)
# ---------------------------------------------------------------------------
if [[ $NGINX_CHANGED -eq 1 ]]; then
  echo ""
  echo "==> Étape 9 — Reload Nginx (vhost / install.sh a changé — vérifie côté config si besoin)"
  nginx -t && systemctl reload nginx
else
  echo ""
  echo "==> Étape 9 — Nginx reload skip (vhost inchangé)"
fi

# ---------------------------------------------------------------------------
# 10. Récap final
# ---------------------------------------------------------------------------
END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

echo ""
echo "============================================================"
echo "  Upgrade terminé en ${DURATION}s"
echo "============================================================"
echo "  Branche  : $BRANCH"
echo "  Commit   : $(git -C "$WORK_DIR" rev-parse --short HEAD)"
if [[ $ALREADY_UP_TO_DATE -eq 0 ]]; then
  echo "  Mises à jour appliquées :"
  [[ $REQ_CHANGED -eq 1 ]]      && echo "    - deps Python (pip)"
  [[ $PKG_CHANGED -eq 1 ]]      && echo "    - deps frontend (yarn)"
  [[ $FRONTEND_CHANGED -eq 1 ]] && echo "    - build frontend"
  [[ $BACKEND_CHANGED -eq 1 ]]  && echo "    - code backend"
  [[ $NGINX_CHANGED -eq 1 ]]    && echo "    - config Nginx/systemd (relance recommandée via install.sh si besoin)"
else
  echo "  Code inchangé, restart backend uniquement (force-reload des modules)."
fi
echo ""
echo "  Logs    : journalctl -u storm-monitor -f"
echo "  Status  : systemctl status storm-monitor"
echo ""
echo "  Pour revenir à un .env précédent :"
echo "    ls -lta $APP_DIR/backend/.env.backups/"
echo "    cp $APP_DIR/backend/.env.backups/.env.YYYYMMDD... $APP_DIR/backend/.env"
echo "    systemctl restart storm-monitor"
echo ""
