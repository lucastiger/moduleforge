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
# A zone can run out of a machine type (ZONE_RESOURCE_POOL_EXHAUSTED for n2-highmem-32 in us-central1-a,
# 2026-10-06). The CPU quota is regional, so try the region's other zones before giving up; any other error stops.
ZONES="$ZONE $(gcloud compute zones list --filter="region:$REGION AND status:UP" --format='value(name)' | grep -vx "$ZONE" | tr '\n' ' ')"
CREATED=""
for Z in $ZONES; do
  if ERR="$(gcloud compute instances create "$NAME" --zone "$Z" --machine-type "$TYPE" \
      --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud \
      --boot-disk-size 200GB --boot-disk-type pd-balanced ${SPOT[@]+"${SPOT[@]}"} --quiet 2>&1 > /dev/null)"; then
    ZONE="$Z"; CREATED=1; break
  fi
  if echo "$ERR" | grep -qE "ZONE_RESOURCE_POOL_EXHAUSTED|resource_availability|does not have enough resources"; then
    echo "$TYPE is unavailable in $Z; trying the next zone" >&2; continue
  fi
  echo "$ERR" >&2; exit 1
done
[ -n "$CREATED" ] || { echo "$TYPE is unavailable in every zone of $REGION: retry later or pass another type/zone" >&2; exit 1; }
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
gcloud compute ssh "$NAME" --zone "$ZONE" --quiet --command "$REMOTE"
# The job runs detached on the VM, so a dropped connection (network blip, the Mac sleeping) does not kill it; this
# script polls for its exit code and copies the results back whether or not it succeeded. A VM-side shutdown after
# MF_GCP_MAX_HOURS stops a VM this script can no longer delete.
if [ "$MODE" = exp ]; then
  JOB="uv run mfos exp run $EID --force"; FETCH="experiments/results/$EID"
else
  JOB="$CMD"
fi
printf 'set -uo pipefail\nexport PATH="$HOME/.local/bin:$PATH"\ncd ~/mf\n%s\n' "$JOB" > "$WORK/job.sh"
gcloud compute scp --zone "$ZONE" --quiet "$WORK/job.sh" "$NAME:job.sh" > /dev/null
MAXH="${MF_GCP_MAX_HOURS:-6}"
gcloud compute ssh "$NAME" --zone "$ZONE" --quiet --command "sudo shutdown -h +$((MAXH * 60)) > /dev/null 2>&1; nohup bash -c 'bash ~/job.sh > ~/job.log 2>&1; echo \$? > ~/job.rc' > /dev/null 2>&1 < /dev/null &"
echo "job started on $NAME: $JOB"
RC=""
DEADLINE=$((SECONDS + MAXH * 3600))
while [ -z "$RC" ] && [ $SECONDS -lt $DEADLINE ]; do
  sleep 30
  RC="$(gcloud compute ssh "$NAME" --zone "$ZONE" --quiet --command 'cat ~/job.rc 2> /dev/null' 2> /dev/null | tr -d '[:space:]' || true)"
done
[ -n "$RC" ] || { echo "job did not finish within ${MAXH} h" >&2; RC=124; }
gcloud compute scp --zone "$ZONE" --quiet "$NAME:job.log" "$WORK/job.log" > /dev/null 2>&1 || true
echo "--- job exit $RC; last lines of its log:"; tail -15 "$WORK/job.log" 2> /dev/null || true
mkdir -p "$(dirname "$FETCH")"
if gcloud compute scp --zone "$ZONE" --quiet --recurse "$NAME:mf/$FETCH" "$WORK/fetched" > /dev/null 2>&1; then
  mkdir -p "$FETCH"; cp -R "$WORK/fetched/." "$FETCH/"
  echo "copied $FETCH back"
  [ "$MODE" = exp ] && echo "the orchestrator picks the results up on its next tick"
else
  echo "nothing to copy back at $FETCH" >&2
fi
exit "$RC"
