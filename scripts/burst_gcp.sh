#!/usr/bin/env bash
# Google Compute Engine counterpart of scripts/burst.sh: run ONE registered experiment, or one repository command,
# on an ephemeral VM, copy the results back, delete the VM. The VM is deleted on every exit path (trap). The code
# reaches the VM only as a git bundle, so no GitHub credentials ever do. Results keep full provenance.
#
# Usage:
#   scripts/burst_gcp.sh --check [machine-type] [zone]          verify gcloud auth, project, API and CPU quota
#   scripts/burst_gcp.sh E001 [machine-type] [zone]             mfos exp run E001 --force; copy experiments/results/E001
#   scripts/burst_gcp.sh --cmd "<command>" <path> [machine-type] [zone]
#                                                               run <command> in the repo; copy <path> back to the same
#                                                               relative path here (for benchmarks and spikes)
# Defaults: n2-highmem-32 (32 vCPU, 256 GB) in us-central1-a. MF_GCP_SPOT=1 uses a Spot VM (cheaper, can be
# preempted: fine for benchmarks, not for a registered run). MF_REF=<ref> bundles another committed ref (default main).
# Setup (once): docs/INFRASTRUCTURE.md, "Burst compute on Google Cloud".
set -euo pipefail
MODE=exp
case "${1:-}" in
  --check) MODE=check; shift ;;
  --cmd) MODE=cmd; CMD="${2:?--cmd needs a command}"; FETCH="${3:?--cmd needs a path to copy back}"; shift 3 ;;
  ""|-*) echo "usage: scripts/burst_gcp.sh --check | <EXPERIMENT_ID> | --cmd \"<command>\" <path>  [machine-type] [zone]" >&2; exit 2 ;;
  *) EID="$1"; shift ;;
esac
TYPE="${1:-n2-highmem-32}"; ZONE="${2:-us-central1-a}"; REGION="${ZONE%-*}"; REF="${MF_REF:-main}"
command -v gcloud > /dev/null || { echo "gcloud is not installed: brew install --cask google-cloud-sdk" >&2; exit 1; }
PROJECT="$(gcloud config get-value project 2> /dev/null || true)"
[ -n "$PROJECT" ] || { echo "no gcloud project set: gcloud config set project <PROJECT_ID>" >&2; exit 1; }
cd "$(git rev-parse --show-toplevel)"

if [ "$MODE" = check ]; then
  echo "account: $(gcloud auth list --filter=status:ACTIVE --format='value(account)')"
  echo "project: $PROJECT"
  gcloud services list --enabled --filter=name:compute.googleapis.com --format='value(name)' | grep -q compute \
    || { echo "Compute Engine API is not enabled: gcloud services enable compute.googleapis.com" >&2; exit 1; }
  VCPU="$(gcloud compute machine-types describe "$TYPE" --zone "$ZONE" --format='value(guestCpus)')"
  echo "machine type: $TYPE in $ZONE ($VCPU vCPU, $(gcloud compute machine-types describe "$TYPE" --zone "$ZONE" --format='value(memoryMb)') MB)"
  gcloud compute regions describe "$REGION" --format=json | python3 -c "
import json, sys
q = {x['metric']: (x['limit'], x['usage']) for x in json.load(sys.stdin)['quotas']}
fam = '$TYPE'.split('-')[0].upper() + '_CPUS'
need = int('$VCPU')
ok = True
for m in ('CPUS', fam):
    if m in q:
        lim, use = q[m]
        print(f'quota {m} in $REGION: {use:.0f} used of {lim:.0f}')
        ok &= lim - use >= need
print('enough quota for one VM' if ok else f'NOT enough quota for {need} vCPU: request an increase (IAM & Admin > Quotas)')
sys.exit(0 if ok else 1)"
  exit 0
fi

if [ "$MODE" = exp ]; then
  test -f "experiments/specs/$EID.yaml" || { echo "$EID is not registered (experiments/specs/$EID.yaml missing)" >&2; exit 1; }
  if [ -n "$(git status --porcelain --untracked-files=no -- src experiments/runners tools pyproject.toml uv.lock)" ]; then
    echo "uncommitted code changes: the experiment must run on a commit that is on main" >&2; exit 1
  fi
  TAG="$(echo "$EID" | tr '[:upper:]' '[:lower:]')"
else
  TAG=cmd
fi
NAME="mf-burst-$TAG-$(date +%s)"
WORK="$(mktemp -d)"
git bundle create -q "$WORK/mf.bundle" "$REF"
SPOT=()
[ "${MF_GCP_SPOT:-0}" = 1 ] && SPOT=(--provisioning-model=SPOT --instance-termination-action=DELETE)
gcloud compute instances create "$NAME" --zone "$ZONE" --machine-type "$TYPE" \
  --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud \
  --boot-disk-size 200GB --boot-disk-type pd-balanced ${SPOT[@]+"${SPOT[@]}"} --quiet > /dev/null
trap 'echo "deleting $NAME"; gcloud compute instances delete "$NAME" --zone "$ZONE" --quiet > /dev/null 2>&1 || echo "DELETE FAILED: remove $NAME by hand" >&2' EXIT
echo "$NAME ($TYPE, $ZONE)"
for _ in $(seq 1 60); do
  gcloud compute ssh "$NAME" --zone "$ZONE" --quiet --command true > /dev/null 2>&1 && break; sleep 5
done
gcloud compute scp --zone "$ZONE" --quiet "$WORK/mf.bundle" "$NAME:mf.bundle" > /dev/null
REMOTE='set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq && sudo apt-get install -y -qq git build-essential curl > /dev/null
curl -LsSf https://astral.sh/uv/install.sh | sh > /dev/null
export PATH="$HOME/.local/bin:$PATH"
git clone -q ~/mf.bundle ~/mf && cd ~/mf && git checkout -q '"$REF"'
scripts/provision_compute.sh
uv sync -q --all-groups
echo "host: $(hostname), $(nproc) vCPU, $(free -g | awk "/Mem:/ {print \$2}") GB"'
if [ "$MODE" = exp ]; then
  gcloud compute ssh "$NAME" --zone "$ZONE" --quiet --command "$REMOTE
uv run mfos exp run $EID --force"
  gcloud compute scp --zone "$ZONE" --quiet --recurse "$NAME:mf/experiments/results/$EID" "$WORK/" > /dev/null
  mkdir -p "experiments/results/$EID"
  cp -R "$WORK/$EID/." "experiments/results/$EID/"
  echo "results copied to experiments/results/$EID/; the orchestrator picks them up on its next tick"
else
  gcloud compute ssh "$NAME" --zone "$ZONE" --quiet --command "$REMOTE
$CMD"
  mkdir -p "$(dirname "$FETCH")"
  gcloud compute scp --zone "$ZONE" --quiet --recurse "$NAME:mf/$FETCH" "$(dirname "$FETCH")/" > /dev/null
  echo "copied $FETCH back"
fi
