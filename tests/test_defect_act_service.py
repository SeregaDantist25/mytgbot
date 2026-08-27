# -*- coding: utf-8 -*-

from io import BytesIO

from openpyxl import load_workbook

from services.defect_act_service import DefectActError, generate_defect_act


def test_generate_defect_act_fills_template():
    result = generate_defect_act(
        {
            "act_number": "4.10",
            "act_date": "27.08.2026",
            "ship": "Славянская",
            "order_number": "24-01",
            "repair_item": "4.10",
            "manager": "С. В. Бачурин",
            "equipment": "Воздушный клапан Ду-25",
            "repair_category": "Текущий ремонт",
            "work_summary": "Дефектация двух воздушных клапанов",
            "basis": "Ремонтная ведомость",
            "rows": [{
                "defect": "Износ уплотнительных поверхностей",
                "work": "Разобрать, дефектовать, восстановить и испытать",
                "unit": "шт.",
                "qty": 2,
            }],
            "conclusion": "Клапаны подлежат ремонту с последующим испытанием.",
        }
    )

    sheet = load_workbook(BytesIO(result))["Акт дефектации"]
    assert sheet["A6"].value == "№ 4.10"
    assert sheet["A8"].value == "Объект ремонта: Славянская"
    assert sheet["A14"].value == "1"
    assert sheet["E14"].value == "2"
    assert sheet["A15"].value == ""
    assert "{{" not in " ".join(
        str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value
    )


def test_generate_defect_act_expands_table():
    result = generate_defect_act({"rows": [{"defect": str(i)} for i in range(15)]})
    sheet = load_workbook(BytesIO(result))["Акт дефектации"]
    assert sheet["B28"].value == "14"
