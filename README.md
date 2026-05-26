# KBOScore Rainmeter Skin

KBO 공식 웹사이트 데이터를 이용해 KBO 경기 일정, 점수, 일자별 팀 순위를 포스터 스타일로 표시하는 Rainmeter 스킨입니다.

![KBOScore screenshot](screenshot.png)

## Files

- `KBOScore_v1.6.ini`: Rainmeter 스킨 본체
- `@Resources/kbo_parser.py`: KBO 경기/순위 데이터 파서
- `@Resources/poster_bg.png`: 포스터 배경 이미지
- `@Resources/kbo_data.inc`: 초기 표시용 데이터 파일

## Install Rainmeter

1. [Rainmeter 공식 사이트](https://www.rainmeter.net/)에서 Rainmeter를 다운로드해 설치합니다.
2. 이 저장소를 다운로드하거나 압축을 풀어 Rainmeter 스킨 폴더에 넣습니다.
   보통 위치는 `내 문서\Rainmeter\Skins\KBOScore`입니다.
3. Rainmeter를 실행한 뒤 관리 창에서 `KBOScore` 폴더를 새로고침합니다.
4. `KBOScore_v1.6.ini`를 선택하고 `로드`를 누릅니다.

## Usage

1. 이 폴더를 Rainmeter `Skins` 폴더 아래에 둡니다.
2. Rainmeter에서 `KBOScore_v1.6.ini`를 로드합니다.
3. 상단 버튼으로 어제/오늘/내일 경기 데이터를 이동할 수 있습니다.
4. `KBO PRESENTS` 영역을 클릭하면 KBO 스코어보드 페이지가 열립니다.
5. 오른쪽 아래 `REFRESH`를 누르면 즉시 데이터를 다시 가져옵니다.

Python이 `PATH`에 등록되어 있어야 자동 업데이트가 동작합니다.
