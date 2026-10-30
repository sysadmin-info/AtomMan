#!/usr/bin/env bash
set -Eeuo pipefail
# Run only AFTER explicitly loading the experimental module with enable_ec_reads=1.
command -v stress-ng >/dev/null || { echo 'Install stress-ng: sudo apt install stress-ng' >&2; exit 1; }
command -v sensors >/dev/null || { echo 'Install lm-sensors: sudo apt install lm-sensors' >&2; exit 1; }
shopt -s nullglob
fan_file=''; cpu_file=''
for name_file in /sys/class/hwmon/hwmon*/name; do
  [[ -r "$name_file" ]] || continue
  case "$(cat "$name_file")" in
    atomman_ec_fan) fan_file="${name_file%/name}/fan1_input" ;;
    coretemp) cpu_file="${name_file%/name}/temp1_input" ;;
  esac
done
[[ -r "$fan_file" && -r "$cpu_file" ]] || { echo 'Missing atomman_ec_fan or coretemp temp1_input. Load PoC explicitly first.' >&2; exit 1; }
pid=''
cleanup() {
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    echo 'Stopping CPU workload ...'
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM
sample() {
  local temp rpm
  rpm=$(cat "$fan_file") || return 1
  temp=$(cat "$cpu_file") || return 1
  printf '%s | CPU %2d C | FAN %4d RPM\n' "$(date +%T)" "$((temp / 1000))" "$rpm"
  if (( temp >= 90000 )); then
    echo 'SAFETY STOP: CPU package temp >=90C' >&2
    return 2
  fi
}
echo 'BASELINE: ~15s'
for _ in {1..5}; do sample; sleep 3; done
echo 'STRESS: 4 workers, each 60% for 60s (stop with Ctrl+C)'
stress-ng --cpu 4 --cpu-load 60 --timeout 60s --metrics-brief >/tmp/atomman-ec-stress-ng.log 2>&1 &
pid=$!
for _ in {1..20}; do
  if ! kill -0 "$pid" 2>/dev/null; then break; fi
  sample
  sleep 3
done
wait "$pid" || true
pid=''
echo 'COOLDOWN: ~30s'
for _ in {1..10}; do sample; sleep 3; done
echo 'Done. Remember: sudo rmmod atomman_ec_fan'
