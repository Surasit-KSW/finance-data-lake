---
description: แปลง technical finance/data content ให้เหมาะกับผู้รับที่ไม่ใช่ technical — CFO, Finance Manager, Auditor, หัวหน้าแผนก สร้าง Line message, Email, meeting talking-points, หรือ Excel comment ตามช่องทางที่ระบุ
---

# Finance Talk

เนื้อหาเดิม แต่ปรับรูปแบบให้ตรงกับผู้รับและช่องทาง

ใช้เมื่อต้องการส่งข้อมูลด้านการเงิน/เทคนิคขึ้นไปให้ผู้บริหาร, ทีม audit, หรือฝ่ายที่ไม่ได้เขียนโค้ด — ไม่ว่าจะเป็น ETL error, ตัวเลขผิดพลาด, สถานะ close, หรือผล data analysis

## เมื่อไหร่ที่ควรใช้

- "เขียน Line ให้หัวหน้า / CFO / Finance Manager / Auditor"
- "สรุปสั้นๆ สำหรับ management meeting"
- "ทำ email update เรื่องนี้"
- "ทำ comment ใน Excel ให้ auditor อ่าน"
- "แปลง technical เป็นภาษาคน"
- "สรุปผล close / variance / reconcile ให้ผู้บริหาร"

ถ้าไม่ชัดว่าช่องทางไหน ถามหนึ่งคำถามแล้วหยุด: *"Line, Email, meeting, หรือ Excel comment?"*

## Audience — ผู้รับคือใคร

ผู้บริหารและทีมการเงินที่ไม่ได้เขียนโค้ด: CFO, Finance Manager, Chief Accountant, Internal Auditor, Department Head

สิ่งที่เขาต้องการรู้: *ตัวเลขถูกไหม, กระทบอะไร, ใครรับผิดชอบ, ขั้นตอนต่อไปคืออะไร*

สิ่งที่เขาไม่ต้องการ: ชื่อ function, SQL query, file path, ชื่อ DuckDB view

## Tone

**เก็บไว้:** GL account code (4111010), period (มี.ค. 2026, 2026-03), SAP transaction codes (FBL3N, VF05, MB52), ชื่อ report (TB, Lead Sheet, AR Aging), ชื่อ plant/cost center (Plant 1100, 1200, 1300), ชื่อ company (AMC, GA), ยอดเงิน (THB), reference number

**ตัดออก:** ชื่อ function Python, file path, SQL query, ชื่อ DuckDB view (v_gl, v_ar), API endpoint, `query_df()`, `.parquet`, error stack trace, ชื่อ library

**แปลง:** mechanism → ผลกระทบเป็นภาษาธุรกิจ ไม่ใช่ "ETL script ใช้ strftime แทน EXTRACT" แต่คือ "ระบบดึงข้อมูลวันที่ผิด ทำให้ยอดบางรายการหายไป" — แปลให้ตรงโดยไม่โกหก

**ภาษา:** ภาษาไทยถ้าผู้รับเป็นทีมในประเทศ ภาษาอังกฤษถ้าเป็น regional/international ถามถ้าไม่ชัด

**หลีกเลี่ยง:**
- คาดเดาหรือพูดก่อนที่จะมีข้อมูลครบ ("น่าจะ", "อาจจะ") — ถ้าไม่รู้ บอกตรงๆ
- อธิบาย background ที่ผู้รับรู้อยู่แล้ว ("GL คือ General Ledger ซึ่งใช้บันทึก...")
- บอกผู้รับว่าต้องตัดสินใจอย่างไร — ให้ข้อมูล, เขาตัดสินใจเอง

## รูปแบบตามช่องทาง

### Line message

ข้อความเดียว กระชับ เข้าใจในทีแรก

- **บรรทัดแรก: สรุปสั้นมาก** ผู้รับอ่านแล้วเข้าใจทันที
- 2–3 bullet สั้น: กระทบอะไร, ใครดูแล, ขั้นต่อไป
- ไม่ต้องมีหัวข้อ bold หนัก — อ่านบน mobile
- เป้าหมาย: ไม่เกิน 80 คำ สำหรับข้อความแรก

### Email — internal ถึงผู้บริหาร / ทีม

Subject line คือครึ่งหนึ่งของคุณค่า

- **Subject:** สรุปเนื้อหาเป็น noun phrase — *"ยอด AR aging มี.ค. 2026: พร้อมส่ง Auditor"* / *"GL Account 4111010 ยอดคลาดเคลื่อน — แก้ไขแล้ว"*
- **Greeting:** ตามระดับความสัมพันธ์ (*เรียน คุณ...* / *Hi,*)
- **เนื้อหา:** สรุปสถานะ → กระทบอะไร → แก้ไขอย่างไร → ขั้นต่อไป เป็น paragraph ไหลตามกัน 2–3 ย่อหน้า
- **ปิด:** ระบุถ้ามี action ที่ต้องการจากผู้รับ — ถ้าไม่มีก็ปิดสั้นๆ

### Meeting talking-points

จะพูด ไม่ใช่อ่าน

- Bullet สั้น หนึ่ง clause ต่อ bullet
- เรียงตามลำดับที่จะพูด
- ใส่ตัวเลข/period ที่จะอ้างถึงไว้ใน bullet เลย ไม่ต้องจำแยก
- ไม่ต้องมี prose — *"ยอด TB มี.ค. 2026 — reconcile กับ SAP แล้ว"* / *"GL 4111010 พบ variance 85,000 THB — แก้ไขแล้วใน pipeline"*

### Excel comment / note

ใส่ใน cell comment หรือ note ของ workbook ให้ auditor อ่าน

- สั้น แต่ครบ: เกิดอะไร, แก้ไขอย่างไร, ใครตรวจสอบ, วันที่
- ไม่ต้องมี greeting
- อ้างถึง GL account code, period, SAP doc number ที่เกี่ยวข้องได้เลย
- ตัวอย่าง: *"ยอด per GL FBL3N ณ 31 มี.ค. 2026: 1,250,000 THB ตรงกับ TB — ตรวจสอบโดย [ชื่อ] วันที่ DD/MM/YYYY"*

## ข้อมูลต้นทาง

Input อาจเป็น:
1. **technical output** จาก Claude — เช่น scrutinize findings, debug session, ETL error message → reframe จาก context นี้
2. **ข้อความ technical** ที่ user paste มา → ใช้โดยตรง
3. **คำถามกว้างๆ** เช่น "สรุปสถานะ close เดือนนี้" → ถามว่าข้อมูลต้นทางอยู่ที่ไหน

ถ้าต้นทางไม่ชัด ถามหนึ่งคำถามแล้วหยุด

## Output flow

1. **ยืนยันช่องทาง** ถ้ายังไม่ระบุ
2. **สร้าง draft** เป็น chat block เดียว formatted ตามช่องทาง
3. **ผู้รับเป็นคนส่งเอง** — skill นี้ไม่ส่งผ่าน API หรือ LINE/email ใดๆ ทั้งสิ้น
4. **แก้ได้ 1 รอบปกติ 3 รอบคือ signal** — ถ้าถึงรอบ 3 ให้ถามว่า framing หรือ audience ผิดตรงไหน

## ตัวอย่าง — scrutinize findings → 3 ช่องทาง

**ต้นทาง (technical):**
> audit_data.py:67 — silent exception fallback drops customer filter. When v_ar query fails, fallback query returns all customers instead of filtered set. audit-reconcile consumers receive wrong data with no error signal.

### Line message

> **พบปัญหา AR aging: filter ลูกค้าไม่ทำงานกรณี query ล้มเหลว**
>
> - ระบบส่งข้อมูล AR ของลูกค้าทุกรายแทนที่จะ filter เฉพาะรายที่ขอ
> - กระทบ: รายงาน audit-reconcile ที่ใช้ filter ลูกค้าเฉพาะราย
> - แก้ไขแล้ว — รอ deploy รอบถัดไป

### Email

> **Subject: แก้ไขปัญหา AR Aging filter — พร้อม deploy**
>
> เรียน คุณ...,
>
> พบปัญหาใน endpoint AR Aging ที่ใช้สำหรับ audit reconciliation: เมื่อระบบ query ข้อมูลไม่สำเร็จ จะแสดงข้อมูล AR ของลูกค้าทุกราย แทนที่จะ filter เฉพาะรายที่ระบุ — โดยไม่มี error แจ้งให้ทราบ
>
> ผลกระทบ: รายงานที่ดึงเฉพาะลูกค้าบางรายอาจได้ข้อมูลครบทุกรายแทน กระทบความถูกต้องของ AR aging ที่ส่ง auditor
>
> แก้ไขแล้ว รอ deploy รอบถัดไป หากต้องการ AR aging ที่ถูกต้องก่อน deploy สามารถขอ export ตรงจากระบบได้

### Meeting talking-points

> - AR aging endpoint — พบว่า filter ลูกค้าล้มเหลวแบบเงียบ
> - กระทบรายงาน audit-reconcile ที่ filter เฉพาะลูกค้า
> - แก้ไขแล้ว รอ deploy — ไม่กระทบยอดในระบบ SAP
> - ถ้า auditor ต้องการข้อมูล AR ก่อน deploy ดึงจาก FBL5N โดยตรง

---

## Rules

- **ห้ามสร้างข้อมูลที่ไม่มีอยู่จริง** — ถ้า root cause ยังไม่รู้ ให้บอกตรงๆ ว่ายังไม่รู้ ไม่ใช่แต่งเพื่อให้ดูน่าเชื่อถือ
- **ห้าม strip GL account code, period, SAP doc number, ชื่อ report** — สิ่งเหล่านี้คือ bridge ระหว่าง data กับผู้รับ ถ้าหาย tracking ขาด
- **ห้ามระบุ owner ถ้าไม่รู้** — ถามผู้ใช้ก่อน
- **ห้ามส่งผ่าน API, LINE, Email จาก skill นี้** — draft ให้ผู้ใช้ส่งเอง
- **อยู่ในฐานะ status update ไม่ใช่ recommendation** — ถ้าต้องการ memo เสนอแนะ ยืนยันก่อนเปลี่ยน framing
