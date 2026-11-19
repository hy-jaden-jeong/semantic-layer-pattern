#!/usr/bin/env bash
# shop-bi semantic layer 정의 폴더를 찾는다. stdout 한 줄 = 정의 폴더 절대 경로. 알림은 stderr의 key=value 줄.
#
# 사용: locate.sh
#   늘 origin/main의 정의를 읽는다(docs/decisions.md D38). 작업 디렉터리가 정의 저장소 checkout이어도 working tree가 아니라 origin/main을 받아 쓴다.
#
# 매 실행마다 먼저 이 skill이 든 저장소가 skill 저장소(SKILLS_REPO) clone이면
# 확인하고, 뒤처졌으면 갱신한다(D37). 다른 저장소에 복사한 skill은 갱신하지 않는다(skill_freshness=unmanaged).
# 종료 코드
#   0 성공
#   2 git 없음
#   3 main에 semantic layer가 없음
#   4 받지 못했고 가진 정의도 없음
#   5 skill이 정의 형식보다 낡았거나 index.md 형식 오류
#   6 skill 저장소를 자동 갱신할 수 없음
# 시험용 환경 변수: SHOP_BI_URL(정의 저장소 주소), SHOP_BI_CACHE(cache 폴더), SHOP_SKILLS_URL(skill 저장소 주소)
set -u
say() { echo "$*" >&2; }
command -v git >/dev/null 2>&1 || { say "error=git이 없다. git을 설치한 뒤 다시 실행한다"; exit 2; }

# 옮겨 쓸 때 이 두 줄을 바꾼다. 원래 설계는 정의 저장소와 skill 저장소가 서로 다른 repo다(docs/llm-entry.md).
# 이 아카이브는 둘을 한 repo에 담아 값이 같다.
DEFS_REPO=hy-jaden-jeong/semantic-layer-pattern     # 정의 저장소 <org>/<repo>
SKILLS_REPO=hy-jaden-jeong/semantic-layer-pattern   # skill 저장소 <org>/<repo>
SHOP_BI_URL=${SHOP_BI_URL:-https://github.com/$DEFS_REPO.git}
SHOP_SKILLS_URL=${SHOP_SKILLS_URL:-}
CACHE=${SHOP_BI_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/shop-data-analytics}
SEM=src/bi/semantic
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
command -v timeout >/dev/null || timeout() { shift; "$@"; }   # macOS 기본에 timeout이 없을 때
quiet_fetch() { GIT_TERMINAL_PROMPT=0 timeout 20 git -C "$1" fetch -q origin "${@:2}" >/dev/null 2>&1; }
TMPS=()
cleanup() { [ ${#TMPS[@]} -eq 0 ] || rm -rf "${TMPS[@]}"; }
trap cleanup EXIT

# origin URL이 정확히 <org>/<repo>(끝 .git·/ 선택, https·ssh 모두)이거나 시험용 주소와 같은가
origin_is() {  # $1 = 저장소, $2 = org/repo, $3 = 시험용 주소(빈 값이면 안 봄)
  local url bare
  url=$(git -C "$1" config --get remote.origin.url 2>/dev/null) || return 1
  [ -n "$3" ] && [ "$url" = "$3" ] && return 0
  bare=${url%/}; bare=${bare%.git}
  [[ "$bare" =~ ^(https?://[^/]+/|ssh://[^/]+/|[^/:]+:)"$2"$ ]]
}

# ── 1. skill 자신(D37) ──────────────────────────────────────────────
SKILL_DIR=$(cd "$(dirname "$0")/.." && pwd -P)
read_version() { tr -d ' \r\n\t' < "$SKILL_DIR/VERSION" 2>/dev/null; }
SKILL_UPDATED=0
skill_repo=$(git -C "$SKILL_DIR" rev-parse --show-toplevel 2>/dev/null || true)
if [ -z "$skill_repo" ] || ! origin_is "$skill_repo" "$SKILLS_REPO" "$SHOP_SKILLS_URL"; then
  say "skill_freshness=unmanaged"
  say "notice=이 skill은 skill 저장소 clone이 아니라 자동 갱신하지 않는다(symlink 설치를 권한다)"
elif quiet_fetch "$skill_repo"; then
  branch=$(git -C "$skill_repo" rev-parse --abbrev-ref HEAD)
  default=$(git -C "$skill_repo" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
  default=${default:-main}
  behind=$(git -C "$skill_repo" rev-list --count "HEAD..origin/$default" 2>/dev/null || echo 0)
  if [ "$behind" -gt 0 ]; then
    # bytecode(__pycache__, *.pyc)는 고친 파일로 보지 않는다
    dirty=$(git -C "$skill_repo" status --porcelain | grep -vE '(^.. |/)__pycache__(/|/?"?$)|\.pyc"?$' || true)
    if [ "$branch" != "$default" ]; then
      say "error=skill 저장소가 $behind commit 뒤처졌는데 $default 브랜치가 아니다(지금 $branch)."
      say "error=직접 정리하고 실행: git -C \"$skill_repo\" checkout $default && git -C \"$skill_repo\" pull --ff-only"
      exit 6
    elif [ -n "$dirty" ]; then
      say "error=skill 저장소가 $behind commit 뒤처졌는데 고친 파일이 있다."
      say "error=직접 정리하고 실행: git -C \"$skill_repo\" status && git -C \"$skill_repo\" pull --ff-only"
      exit 6
    elif git -C "$skill_repo" pull -q --ff-only origin "$default" >/dev/null 2>&1; then
      SKILL_UPDATED=1
      say "skill_updated=1 behind_was=$behind"
      say "notice=skill을 갱신했다. SKILL.md를 다시 읽고 따른다"
    else
      say "error=skill 저장소를 fast-forward로 갱신하지 못했다. 실행: git -C \"$skill_repo\" pull --ff-only"
      exit 6
    fi
  fi
else
  say "skill_freshness=unknown"
fi
SKILL_VERSION=$(read_version)   # 갱신을 시도한 뒤의 version으로 skill_min과 견준다(D40)
[ -n "$SKILL_VERSION" ] || SKILL_VERSION=0
[[ "$SKILL_VERSION" =~ ^[0-9]+$ ]] || { say "error=skill의 VERSION 파일 형식 오류(정수가 아님: $SKILL_VERSION)"; exit 5; }

# ── 2. 정의 폴더(D38, D39) ─────────────────────────────────────────
is_shop_bi() {  # 작업 디렉터리가 정의 저장소 checkout이면 그 최상위 경로
  local top
  top=$(git rev-parse --show-toplevel 2>/dev/null) || return 1
  origin_is "$top" "$DEFS_REPO" "$SHOP_BI_URL" && echo "$top"
}
check_format() {  # $1 = 정의 폴더. index.md 첫머리 format·skill_min(D40)
  local idx="$1/index.md" l1 l2 fmt min
  [ -f "$idx" ] || { say "error=${1}에 index.md가 없다(semantic layer 없음)"; exit 3; }
  l1=$(sed -n 1p "$idx" | tr -d '\r'); l2=$(sed -n 2p "$idx" | tr -d '\r')
  case "$l2" in skill_min:*) ;; *) say "error=index.md 형식 오류: 둘째 줄이 'skill_min: <정수>'가 아니다($l2)"; exit 5 ;; esac
  min=$(echo "${l2#skill_min:}" | tr -d ' \t')
  [[ "$min" =~ ^[0-9]+$ ]] || { say "error=index.md 형식 오류: skill_min이 정수가 아니다($min)"; exit 5; }
  if [ "$min" -gt "$SKILL_VERSION" ]; then
    if [ "$SKILL_UPDATED" = 1 ]; then
      say "error=정의가 skill version $min 이상을 요구한다(갱신한 뒤에도 지금 $SKILL_VERSION). skill 저장소의 기본 브랜치에 새 version이 올라올 때까지 기다리거나 관리자에게 알린다"
    else
      say "error=정의가 skill version $min 이상을 요구한다(지금 $SKILL_VERSION). skill 저장소를 갱신한다"
    fi
    exit 5
  fi
  fmt=${l1#format: }
  [ "$fmt" = 1 ] || say "notice=index.md format ${fmt}은 이 skill이 모르는 형식이다. README.md를 우선한다"
}

# cache 구조: $CACHE/sha-<full sha>/semantic(내용은 sha마다 고정) + $CACHE/current(1줄 sha, 2줄 확인 시각).
# 실행마다 고유한 임시 폴더에 받은 뒤 rename으로 들이고, current도 임시 파일을 rename해 바꾼다.
# 동시에 돌아도 이미 알려 준 경로가 사라지지 않도록, 옛 sha 폴더는 하루 넘게 안 쓴 것만 치운다.
cache_sha() { sed -n 1p "$CACHE/current" 2>/dev/null; }
cache_checked() { sed -n 2p "$CACHE/current" 2>/dev/null; }
cache_dir() { local s; s=$(cache_sha); [ -n "$s" ] && [ -f "$CACHE/sha-$s/semantic/index.md" ] && echo "$CACHE/sha-$s/semantic"; }
new_tmp() {  # 고유한 임시 폴더를 만들어 NEWTMP에 둔다(끝나면 지운다)
  NEWTMP=$(mktemp -d "$CACHE/.tmp.XXXXXX") || { say "error=cache 폴더에 쓸 수 없다($CACHE)"; exit 4; }
  TMPS+=("$NEWTMP")
}
set_current() {  # $1 = sha, $2 = 확인 시각
  local f="$CACHE/.current.$$.$RANDOM"
  touch "$CACHE/sha-$1" 2>/dev/null   # 쓰는 중인 sha 폴더는 정리 대상에서 빠지게 한다
  printf '%s\n%s\n' "$1" "$2" > "$f" && mv -f "$f" "$CACHE/current"
}
install_cache() {  # $1 = 받은 semantic 폴더(cache 안의 임시 폴더), $2 = full sha, $3 = 확인 시각
  local dest="$CACHE/sha-$2" i j
  if [ ! -f "$dest/semantic/index.md" ]; then
    for i in 1 2; do
      if mkdir "$dest" 2>/dev/null; then   # mkdir가 성공한 실행 하나만 semantic을 rename으로 들인다
        mv "$1" "$dest/semantic" 2>/dev/null || rmdir "$dest" 2>/dev/null
        break
      fi
      for j in $(seq 50); do [ -f "$dest/semantic/index.md" ] && break 2; sleep 0.1; done
      rmdir "$dest" 2>/dev/null   # 비어 있으면 앞선 실행이 도중에 멈춘 것. 한 번 더 시도한다
    done
  fi
  [ -f "$dest/semantic/index.md" ] || { say "error=cache에 정의를 들이지 못했다($dest)"; exit 4; }
  set_current "$2" "$3"
  find "$CACHE" -maxdepth 1 \( -name 'sha-*' -o -name '.tmp.*' -o -name '.current.*' \) -mmin +1440 \
       ! -name "sha-$2" ! -name "sha-$(cache_sha)" -exec rm -rf {} + 2>/dev/null || true
}
short() { echo "${1:0:7}"; }
use_cache() {  # 최신 확인 실패 시(D39). cache가 없으면 그냥 돌아온다
  local s d
  s=$(cache_sha); d="$CACHE/sha-$s/semantic"
  [ -n "$s" ] && [ -f "$d/index.md" ] || return 0
  say "source=cache ref=main@$(short "$s") freshness=unknown last_checked=$(cache_checked)"
  say "notice=최신 확인 못 함. 답 끝 ref에 그대로 적는다"
  check_format "$d"; echo "$d"; exit 0
}

top=$(is_shop_bi || true)
mkdir -p "$CACHE" || { say "error=cache 폴더를 만들 수 없다($CACHE)"; exit 4; }
from_checkout() {  # $1 = checkout, $2 = sha, $3 = 확인 시각. origin/main의 정의를 cache에 들인다
  if [ "$(cache_sha)" != "$2" ] || ! cache_dir >/dev/null; then
    new_tmp
    git -C "$1" archive "$2" "$SEM" 2>/dev/null | tar -x -C "$NEWTMP" 2>/dev/null
    [ -f "$NEWTMP/$SEM/index.md" ] || { say "error=origin/main에서 ${SEM}을 꺼내지 못했다"; exit 4; }
    install_cache "$NEWTMP/$SEM" "$2" "$3"
  else
    set_current "$2" "$3"
  fi
}
main_fetched_at() {  # $1 = checkout. main을 마지막으로 받은 시각(UTC). FETCH_HEAD 다음 reflog, 모르면 빈 값
  local f t
  f=$(git -C "$1" rev-parse --git-path FETCH_HEAD 2>/dev/null)
  case "$f" in /*) ;; *) f="$1/$f" ;; esac
  if [ -f "$f" ] && grep -q "branch 'main' of" "$f"; then
    t=$(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f" 2>/dev/null)
    [ -n "$t" ] && { date -u -r "$t" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d "@$t" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null; } && return
  fi
  TZ=UTC git -C "$1" log -g -1 --date=format-local:%Y-%m-%dT%H:%M:%SZ --format=%gd refs/remotes/origin/main 2>/dev/null \
    | sed -n 's/.*@{\(.*\)}$/\1/p'
}
if [ -n "$top" ]; then
  fetched_before=$(main_fetched_at "$top")   # 실패한 fetch는 FETCH_HEAD를 비우므로 먼저 읽어 둔다
  if quiet_fetch "$top" "+main:refs/remotes/origin/main"; then   # main을 명시한다(feature만 받은 얕은 checkout도)
    sha=$(git -C "$top" rev-parse -q --verify "origin/main^{commit}" 2>/dev/null) \
      || { say "error=origin/main을 받지 못했다"; exit 4; }
    git -C "$top" cat-file -e "$sha:$SEM/index.md" 2>/dev/null || { say "error=origin/main에 ${SEM}이 없다"; exit 3; }
    from_checkout "$top" "$sha" "$(now)"
    say "source=main ref=main@$(short "$sha") via=checkout"
    d="$CACHE/sha-$sha/semantic"; check_format "$d"; echo "$d"; exit 0   # 알린 sha의 폴더(다른 실행이 current를 바꿔도)
  fi
  # 받기 실패: checkout의 origin/main과 cache 중 더 새로운 것
  sha=$(git -C "$top" rev-parse -q --verify "origin/main^{commit}" 2>/dev/null || true)
  if [ -n "$sha" ] && git -C "$top" cat-file -e "$sha:$SEM/index.md" 2>/dev/null; then
    csha=$(cache_sha)
    if [ -n "$csha" ] && cache_dir >/dev/null && ! git -C "$top" merge-base --is-ancestor "$csha" "$sha" 2>/dev/null; then
      use_cache   # cache가 origin/main보다 새롭다(또는 checkout이 모르는 commit)
    fi
    if [ "$csha" = "$sha" ] && cache_dir >/dev/null; then use_cache; fi
    checked=$fetched_before
    from_checkout "$top" "$sha" "${checked:-unknown}"
    say "source=main ref=main@$(short "$sha") freshness=unknown last_checked=${checked:-unknown}"
    say "notice=최신 확인 못 함. 답 끝 ref에 그대로 적는다"
    d="$CACHE/sha-$sha/semantic"; check_format "$d"; echo "$d"; exit 0   # 알린 sha의 폴더(다른 실행이 current를 바꿔도)
  fi
  use_cache
  say "error=origin/main을 받지 못했고 가진 정의도 없다"; exit 4
fi

# checkout 밖: main의 sha를 보고, cache와 같으면 다시 쓰고 다르면 main만 얕게 받는다
remote=$(GIT_TERMINAL_PROMPT=0 timeout 20 git ls-remote "$SHOP_BI_URL" refs/heads/main 2>/dev/null) || remote=FAIL
if [ "$remote" != FAIL ]; then
  sha=$(echo "$remote" | awk '$2 == "refs/heads/main" {print $1; exit}')
  [ -n "$sha" ] || { say "error=정의 저장소에 main 브랜치가 없다(semantic layer 없음)"; exit 3; }
  if [ "$(cache_sha)" = "$sha" ] && d=$(cache_dir); then
    set_current "$sha" "$(now)"
    say "source=main ref=main@$(short "$sha") via=cache-current"
    check_format "$d"; echo "$d"; exit 0
  fi
  new_tmp; tmp=$NEWTMP
  if GIT_TERMINAL_PROMPT=0 timeout 60 git clone -q --depth 1 --branch main --filter=blob:none --sparse \
       "$SHOP_BI_URL" "$tmp/repo" >/dev/null 2>&1 \
     && git -C "$tmp/repo" sparse-checkout set "$SEM" >/dev/null 2>&1; then
    [ -f "$tmp/repo/$SEM/index.md" ] || { say "error=main에 ${SEM}이 없다"; exit 3; }
    sha=$(git -C "$tmp/repo" rev-parse HEAD)
    install_cache "$tmp/repo/$SEM" "$sha" "$(now)"
    say "source=main ref=main@$(short "$sha") via=clone"
    d="$CACHE/sha-$sha/semantic"; check_format "$d"; echo "$d"; exit 0   # 알린 sha의 폴더(다른 실행이 current를 바꿔도)
  fi
fi
use_cache
say "error=정의 저장소 main을 받지 못했고 가진 정의도 없다(네트워크·권한 확인). checkout 안에서 실행하거나 접근 권한을 확인한다"
exit 4
