"""테스트·통합 테스트용 가상 PDF 생성기. 생성물은 실제 리포트/공시가 아니다.

python tests/fixtures/make_sample_pdf.py <출력.pdf> [report|filing]
"""
from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

REPORT_PAGES = [
    ["[샘플] 가상 매크로 위클리 — 실제 증권사 리포트 아님 (테스트용으로 생성됨)",
     "작성: 샘플하우스 리서치 / 2026.10.23",
     "요약: 미국 고용 둔화로 FOMC가 연내 추가 인하에 나설 가능성이 높다고 본다.",
     "UST 10년물은 단기적으로 하락(금리 기준) 방향을 예상하며, 커브는 스티프닝을 전망한다.",
     "원/달러는 달러 약세 전환에 따라 단기 하락(원화 강세) 쪽으로 기울 것으로 본다.",
     "이 문서는 파이프라인 검증을 위한 가상 텍스트이며 어떠한 실제 의견도 담고 있지 않다."],
    ["2. 크레딧: 국내 회사채 AA- 스프레드는 연말 계절성으로 소폭 확대 가능하나 장기적으로 안정.",
     "리스크: 미국 재정적자 확대에 따른 기간 프리미엄 상승, 지정학 리스크로 인한 유가 급등.",
     "본 샘플은 테스트 전용이다. 투자 판단에 사용하지 말 것."],
]
FILING_PAGES = [
    ["[샘플] 가상 보험사 경영실적 자료 — 실제 공시 아님 (테스트용)",
     "샘플손해보험 2026년 2분기 운용자산 현황 (단위: 십억원)"],
]


def make(out: Path, kind: str = "report") -> Path:
    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    c = canvas.Canvas(str(out), pagesize=A4)
    pages = REPORT_PAGES if kind == "report" else FILING_PAGES
    for lines in pages:
        c.setFont("HYSMyeongJo-Medium", 11)
        y = 800
        for line in lines:
            c.drawString(40, y, line)
            y -= 22
        if kind == "filing":
            rows = [["구분", "금액", "비중"], ["국공채", "20000", "40.0%"], ["회사채", "7500", "15.0%"],
                    ["합계", "50000", "100.0%"]]
            y -= 10
            for r in rows:
                x = 60
                for cell in r:
                    c.rect(x, y - 4, 120, 20)
                    c.drawString(x + 5, y + 2, cell)
                    x += 120
                y -= 20
        c.showPage()
    c.save()
    return out


if __name__ == "__main__":
    make(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "report")
