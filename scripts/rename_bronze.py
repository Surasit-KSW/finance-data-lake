"""
rename_bronze.py — Standardize all Bronze Raw filenames to unified convention.

Convention: {sap_txcode}_{YYYYMM}.xlsx  (all lowercase, ISO date YYYYMM, .xlsx)
Special patterns:
  - Multi-period: {txcode}_{YYYYMM}_{YYYYMM}.xlsx
  - Annual:       {txcode}_{YYYY}.xlsx
  - Suffix:       {txcode}_{YYYYMM}_{suffix}.xlsx  (combined, labour, machine, etc.)
  - Wildcard:     {txcode}_all_{YYYYMM}.xlsx        (all-plant files in /all/ subfolder)

Run from project root:
    python scripts/rename_bronze.py
    python scripts/rename_bronze.py --dry-run
"""
import sys
import os
import shutil
import argparse
from pathlib import Path

ROOT = Path("D:/_Work_Workspace/03_Data_Projects/_Finance_Data_Lake/01_Bronze_Raw")

# ---------------------------------------------------------------------------
# RENAMES: list of (relative_src, relative_dst)
# All paths relative to ROOT
# ---------------------------------------------------------------------------
RENAMES = [
    # ── AR ──────────────────────────────────────────────────────────────────
    ("ar/amc/AR_2024.XLSX",                                         "ar/amc/ar_2024.xlsx"),
    ("ar/amc/AR_2025.XLSX",                                         "ar/amc/ar_2025.xlsx"),

    # ── AP ──────────────────────────────────────────────────────────────────
    ("ap/amc/ap_all.XLSX",                                          "ap/amc/ap_all.xlsx"),
    # deposit_Q4'2025_updated → canonical (keep updated, delete original — see DELETES)
    ("ap/amc/deposit_Q4'2025_updated.xlsx",                         "ap/amc/ap_deposit_202412.xlsx"),
    ("ap/amc/other deposit_all.XLSX",                               "ap/amc/ap_deposit_other_all.xlsx"),

    # ── COST CENTER (KSB1) ──────────────────────────────────────────────────
    ("cost_center/amc/1100/2026/KSB1_1100_01.2026.XLSX",           "cost_center/amc/1100/2026/ksb1_202601.xlsx"),
    ("cost_center/amc/1100/2026/KSB1_1100_02.2026.XLSX",           "cost_center/amc/1100/2026/ksb1_202602.xlsx"),
    ("cost_center/amc/1100/2026/KSB1_1100_03.2026.XLSX",           "cost_center/amc/1100/2026/ksb1_202603.xlsx"),
    ("cost_center/amc/1100/2026/KSB1_1100_04.2026.XLSX",           "cost_center/amc/1100/2026/ksb1_202604.xlsx"),
    ("cost_center/amc/1100/2026/KSB1_1100_05.2026.XLSX",           "cost_center/amc/1100/2026/ksb1_202605.xlsx"),
    ("cost_center/amc/1200/2026/KSB1_1200_01.2026.XLSX",           "cost_center/amc/1200/2026/ksb1_202601.xlsx"),
    ("cost_center/amc/1200/2026/KSB1_1200_02.2026.XLSX",           "cost_center/amc/1200/2026/ksb1_202602.xlsx"),
    ("cost_center/amc/1200/2026/KSB1_1200_03.2026.XLSX",           "cost_center/amc/1200/2026/ksb1_202603.xlsx"),
    ("cost_center/amc/1200/2026/KSB1_1200_04.2026.XLSX",           "cost_center/amc/1200/2026/ksb1_202604.xlsx"),
    ("cost_center/amc/1200/2026/KSB1_1200_05.2026.XLSX",           "cost_center/amc/1200/2026/ksb1_202605.xlsx"),
    ("cost_center/amc/1300/2026/KSB1_1300_01.2026.XLSX",           "cost_center/amc/1300/2026/ksb1_202601.xlsx"),
    ("cost_center/amc/1300/2026/KSB1_1300_02.2026.XLSX",           "cost_center/amc/1300/2026/ksb1_202602.xlsx"),
    ("cost_center/amc/1300/2026/KSB1_1300_03.2026.XLSX",           "cost_center/amc/1300/2026/ksb1_202603.xlsx"),
    ("cost_center/amc/1300/2026/KSB1_1300_04.2026.XLSX",           "cost_center/amc/1300/2026/ksb1_202604.xlsx"),
    ("cost_center/amc/1300/2026/KSB1_1300_05.2026.XLSX",           "cost_center/amc/1300/2026/ksb1_202605.xlsx"),
    ("cost_center/amc/all/2026/KSB1_all_05.2026.XLSX",             "cost_center/amc/all/2026/ksb1_all_202605.xlsx"),
    ("cost_center/ga/2200/2026/KSB1_2200_05.2026.XLSX",            "cost_center/ga/2200/2026/ksb1_202605.xlsx"),

    # ── GL (FBL3N) ──────────────────────────────────────────────────────────
    ("gl/amc/sap_fbl3n.XLSX",                                       "gl/amc/gl_legacy.xlsx"),
    ("gl/amc/2025/gl_2025_12.XLSX",                                 "gl/amc/2025/gl_202512.xlsx"),
    # AMC_GL_* are duplicates of gl_2026_* → see DELETES; keep gl_2026_* and rename:
    ("gl/amc/2026/gl_2026_01.XLSX",                                 "gl/amc/2026/gl_202601.xlsx"),
    ("gl/amc/2026/gl_2026_02.XLSX",                                 "gl/amc/2026/gl_202602.xlsx"),
    ("gl/amc/2026/gl_2026_03.XLSX",                                 "gl/amc/2026/gl_202603.xlsx"),
    ("gl/amc/2026/gl_2026_04.XLSX",                                 "gl/amc/2026/gl_202604.xlsx"),
    ("gl/amc/2026/gl_2026_05.XLSX",                                 "gl/amc/2026/gl_202605.xlsx"),
    # GA GL: GA_2200_04 and GA_GL_04 are duplicates → keep GA_2200_04, delete GA_GL_04
    ("gl/ga/2026/GA_2200_04.2026.XLSX",                             "gl/ga/2026/gl_202604.xlsx"),
    ("gl/ga/2026/GA_GL_01.2026.XLSX",                               "gl/ga/2026/gl_202601.xlsx"),
    ("gl/ga/2026/GA_GL_02.2026.XLSX",                               "gl/ga/2026/gl_202602.xlsx"),
    ("gl/ga/2026/GA_GL_03.2026.XLSX",                               "gl/ga/2026/gl_202603.xlsx"),
    ("gl/ga/2026/GA_GL_05.2026.XLSX",                               "gl/ga/2026/gl_202605.xlsx"),

    # ── INVENTORY ───────────────────────────────────────────────────────────
    # Long Thai filename → short canonical name
    ("inventory/amc/6.3 AMC_\u0e22\u0e2d\u0e14\u0e04\u0e07\u0e40\u0e2b\u0e25\u0e37\u0e2d\u0e02\u0e2d\u0e07\u0e2a\u0e34\u0e19\u0e04\u0e49\u0e32\u0e04\u0e07\u0e40\u0e2b\u0e25\u0e37\u0e2d \u0e08\u0e31\u0e14\u0e1b\u0e23\u0e30\u0e40\u0e20\u0e17\u0e42\u0e14\u0e22\u0e2a\u0e34\u0e19\u0e04\u0e49\u0e32 \u0e13  31.03.2026.xlsx",
                                                                     "inventory/amc/mb52_nrv_audit_202603.xlsx"),
    ("inventory/amc/AMC_TB_03.2026_v9.XLSX",                        "inventory/amc/tb_nrv_202603_v9.xlsx"),
    ("inventory/amc/credit_note_report_2026.xlsx",                   "inventory/amc/credit_note_2026.xlsx"),
    ("inventory/amc/NRV_SKU_Analysis_2026_Q1_v2.xlsx",              "inventory/amc/nrv_sku_202603.xlsx"),
    ("inventory/amc/SO_BL 22.04.69.xlsx",                           "inventory/amc/so_bl_20260422.xlsx"),
    ("inventory/ga/GA_stock_04.2026.XLSX",                          "inventory/ga/mb52_202604.xlsx"),
    # warehouse_stock/amc/2026 misplaced PRD summary
    ("warehouse_stock/amc/2026/AMC_PRD_Q1'2026.XLSX",               "warehouse_stock/amc/2026/mb52_q1_202603.xlsx"),

    # ── MASTER DATA ─────────────────────────────────────────────────────────
    ("master_data/coa/COA_AMC.XLSX",                                "master_data/coa/coa_amc.xlsx"),
    ("master_data/cost_center/Cost_center_master.XLSX",             "master_data/cost_center/cc_master.xlsx"),
    ("master_data/material/MARA_03.2026.XLSX",                      "master_data/material/mara_202603.xlsx"),
    ("master_data/material/MARA_04.2026.XLSX",                      "master_data/material/mara_202604.xlsx"),
    ("master_data/material/MARA_05.2026.XLSX",                      "master_data/material/mara_202605.xlsx"),

    # ── MATERIAL DOCS (MB51) ────────────────────────────────────────────────
    ("material_docs/amc/1100/2026/MB51_1100_05.2026.XLSX",          "material_docs/amc/1100/2026/mb51_202605.xlsx"),
    ("material_docs/amc/1200/2026/MB51_1200_05.2026.XLSX",          "material_docs/amc/1200/2026/mb51_202605.xlsx"),
    ("material_docs/amc/1300/2026/MB51_1300_05.2026.XLSX",          "material_docs/amc/1300/2026/mb51_202605.xlsx"),
    ("material_docs/amc/1300/2026/MB51_HCL_01-05.2026.XLSX",        "material_docs/amc/1300/2026/mb51_hcl_202601_202605.xlsx"),
    ("material_docs/amc/1300/2026/MB51_LNG_01-05.2026.XLSX",        "material_docs/amc/1300/2026/mb51_lng_202601_202605.xlsx"),
    ("material_docs/amc/1300/2026/MB51_stockGI_2025-2026.XLSX",     "material_docs/amc/1300/2026/mb51_gi_2025_2026.xlsx"),
    ("material_docs/amc/1300/2026/MB51_stockGI_30.06.2026.XLSX",    "material_docs/amc/1300/2026/mb51_gi_202606.xlsx"),
    ("material_docs/amc/1300/2026/MB51_ZincZam_01-05.2026.XLSX",    "material_docs/amc/1300/2026/mb51_zinczam_202601_202605.xlsx"),
    ("material_docs/amc/all/2025/MB51_all_plant_12.2025.XLSX",      "material_docs/amc/all/2025/mb51_all_202512.xlsx"),
    ("material_docs/amc/all/2026/MB51_all_plant_01.2026.XLSX",      "material_docs/amc/all/2026/mb51_all_202601.xlsx"),
    ("material_docs/amc/all/2026/MB51_all_plant_02.2026.XLSX",      "material_docs/amc/all/2026/mb51_all_202602.xlsx"),
    ("material_docs/amc/all/2026/MB51_all_plant_03.2026.XLSX",      "material_docs/amc/all/2026/mb51_all_202603.xlsx"),
    ("material_docs/amc/all/2026/MB51_all_plant_04.2026.XLSX",      "material_docs/amc/all/2026/mb51_all_202604.xlsx"),
    ("material_docs/amc/all/2026/MB51_all_plant_05.2026.XLSX",      "material_docs/amc/all/2026/mb51_all_202605.xlsx"),
    ("material_docs/ga/2200/2026/MB51_2200_05.2026.XLSX",           "material_docs/ga/2200/2026/mb51_202605.xlsx"),

    # ── MONTH END (CO Closing) ───────────────────────────────────────────────
    # Plant 1100
    ("month_end/amc/1100/2026/1100_CO88H_05.2026_combined.XLSX",    "month_end/amc/1100/2026/co88h_202605_combined.xlsx"),
    ("month_end/amc/1100/2026/1100_Con2_05.2026.XLSX",              "month_end/amc/1100/2026/con2_202605.xlsx"),
    ("month_end/amc/1100/2026/1100_Con2_05.2026_std.XLSX",          "month_end/amc/1100/2026/con2_202605_std.xlsx"),
    ("month_end/amc/1100/2026/1100_CPTD_05.2026.XLSX",              "month_end/amc/1100/2026/cptd_202605.xlsx"),
    ("month_end/amc/1100/2026/1100_CPTD_05.2026_combined.XLSX",     "month_end/amc/1100/2026/cptd_202605_combined.xlsx"),
    ("month_end/amc/1100/2026/1100_KKAOH_05.2026.XLSX",             "month_end/amc/1100/2026/kkaoh_202605.xlsx"),
    ("month_end/amc/1100/2026/1100_KKS1_05.2026.XLSX",              "month_end/amc/1100/2026/kks1_202605.xlsx"),
    ("month_end/amc/1100/2026/1100_KSII_05.2026.XLSX",              "month_end/amc/1100/2026/ksii_202605.xlsx"),
    ("month_end/amc/1100/2026/1100_KSS2_05.2026.XLSX",              "month_end/amc/1100/2026/kss2_202605.xlsx"),
    ("month_end/amc/1100/2026/1100_KSU5_05.2026_Labout.XLSX",       "month_end/amc/1100/2026/ksu5_labour_202605.xlsx"),
    ("month_end/amc/1100/2026/1100_KSU5_05.2026_machine.XLSX",      "month_end/amc/1100/2026/ksu5_machine_202605.xlsx"),
    ("month_end/amc/1100/2026/1100_KSU5_05.2026_output.XLSX",       "month_end/amc/1100/2026/ksu5_output_202605.xlsx"),
    # Plant 1200
    ("month_end/amc/1200/2026/1200_CO88H_05.2026.XLSX",             "month_end/amc/1200/2026/co88h_202605.xlsx"),
    ("month_end/amc/1200/2026/1200_CO88H_05.2026_combined.XLSX",    "month_end/amc/1200/2026/co88h_202605_combined.xlsx"),
    ("month_end/amc/1200/2026/1200_CON2_05.2026.XLSX",              "month_end/amc/1200/2026/con2_202605.xlsx"),
    ("month_end/amc/1200/2026/1200_CON2_05.2026_combined.XLSX",     "month_end/amc/1200/2026/con2_202605_combined.xlsx"),
    ("month_end/amc/1200/2026/1200_CPTD_05.2026.XLSX",              "month_end/amc/1200/2026/cptd_202605.xlsx"),
    ("month_end/amc/1200/2026/1200_CPTD_05.2026_combined.XLSX",     "month_end/amc/1200/2026/cptd_202605_combined.xlsx"),
    ("month_end/amc/1200/2026/1200_KKAOH_05.2026.XLSX",             "month_end/amc/1200/2026/kkaoh_202605.xlsx"),
    ("month_end/amc/1200/2026/1200_KKS1_05.2026.XLSX",              "month_end/amc/1200/2026/kks1_202605.xlsx"),
    ("month_end/amc/1200/2026/1200_KSII_05.2026.XLSX",              "month_end/amc/1200/2026/ksii_202605.xlsx"),
    ("month_end/amc/1200/2026/1200_KSS2_05.2026.XLSX",              "month_end/amc/1200/2026/kss2_202605.xlsx"),
    ("month_end/amc/1200/2026/1200_KSU5_05.2026_labour.XLSX",       "month_end/amc/1200/2026/ksu5_labour_202605.xlsx"),
    ("month_end/amc/1200/2026/1200_KSU5_05.2026_machinr.XLSX",      "month_end/amc/1200/2026/ksu5_machine_202605.xlsx"),
    ("month_end/amc/1200/2026/1200_KSU5_05.2026_output.XLSX",       "month_end/amc/1200/2026/ksu5_output_202605.xlsx"),
    # Plant 1300
    ("month_end/amc/1300/2026/1300_CPTD_05.2026.XLSX",              "month_end/amc/1300/2026/cptd_202605.xlsx"),
    ("month_end/amc/1300/2026/1300_KSU5_05.2026.XLSX",              "month_end/amc/1300/2026/ksu5_202605.xlsx"),
    ("month_end/amc/1300/2026/1300_KSU5_05.2026_labour.XLSX",       "month_end/amc/1300/2026/ksu5_labour_202605.xlsx"),
    ("month_end/amc/1300/2026/1300_KSU5_05.2026_output.XLSX",       "month_end/amc/1300/2026/ksu5_output_202605.xlsx"),

    # ── PAYROLL ─────────────────────────────────────────────────────────────
    ("payroll/amc/2026/AMC Payroll report 01.2026.csv",             "payroll/amc/2026/payroll_202601.csv"),
    ("payroll/amc/2026/AMC Payroll report 02.2026.csv",             "payroll/amc/2026/payroll_202602.csv"),
    ("payroll/amc/2026/AMC Payroll report 03.2026.csv",             "payroll/amc/2026/payroll_202603.csv"),
    ("payroll/amc/2026/AMC Payroll report 03.2026_\u0e04\u0e33\u0e19\u0e27\u0e13\u0e42\u0e1a\u0e19\u0e31\u0e2a.csv",
                                                                     "payroll/amc/2026/payroll_202603_bonus.csv"),
    ("payroll/amc/2026/AMC Payroll report 04.2026.csv",             "payroll/amc/2026/payroll_202604.csv"),
    ("payroll/amc/mapping/map GL.csv",                              "payroll/amc/mapping/map_gl.csv"),

    # ── PRODUCTION ORDERS (PRD) ──────────────────────────────────────────────
    # AMC Plant 1100
    ("production_orders/amc/1100/2026/PRD_1100_01.2026.XLSX",       "production_orders/amc/1100/2026/prd_202601.xlsx"),
    ("production_orders/amc/1100/2026/PRD_1100_02.2026.XLSX",       "production_orders/amc/1100/2026/prd_202602.xlsx"),
    ("production_orders/amc/1100/2026/PRD_1100_03.2026.XLSX",       "production_orders/amc/1100/2026/prd_202603.xlsx"),
    ("production_orders/amc/1100/2026/PRD_1100_04.2026.XLSX",       "production_orders/amc/1100/2026/prd_202604.xlsx"),
    ("production_orders/amc/1100/2026/PRD_1100_05.2026.XLSX",       "production_orders/amc/1100/2026/prd_202605.xlsx"),
    # AMC Plant 1200
    ("production_orders/amc/1200/2026/PRD_1200_01.2026.XLSX",       "production_orders/amc/1200/2026/prd_202601.xlsx"),
    ("production_orders/amc/1200/2026/PRD_1200_02.2026.XLSX",       "production_orders/amc/1200/2026/prd_202602.xlsx"),
    ("production_orders/amc/1200/2026/PRD_1200_03.2026.XLSX",       "production_orders/amc/1200/2026/prd_202603.xlsx"),
    ("production_orders/amc/1200/2026/PRD_1200_04.2026.XLSX",       "production_orders/amc/1200/2026/prd_202604.xlsx"),
    ("production_orders/amc/1200/2026/PRD_1200_05.2026.XLSX",       "production_orders/amc/1200/2026/prd_202605.xlsx"),
    # AMC Plant 1300
    ("production_orders/amc/1300/2026/PRD_1300_01.2026.XLSX",       "production_orders/amc/1300/2026/prd_202601.xlsx"),
    ("production_orders/amc/1300/2026/PRD_1300_02.2026.XLSX",       "production_orders/amc/1300/2026/prd_202602.xlsx"),
    ("production_orders/amc/1300/2026/PRD_1300_03.2026.XLSX",       "production_orders/amc/1300/2026/prd_202603.xlsx"),
    ("production_orders/amc/1300/2026/PRD_1300_04.2026.XLSX",       "production_orders/amc/1300/2026/prd_202604.xlsx"),
    ("production_orders/amc/1300/2026/PRD_1300_05.2026.XLSX",       "production_orders/amc/1300/2026/prd_202605.xlsx"),
    # GA Plant 2200
    ("production_orders/ga/2200/2026/GA_PRD_01.2026.XLSX",          "production_orders/ga/2200/2026/prd_202601.xlsx"),
    ("production_orders/ga/2200/2026/GA_PRD_02.2026.XLSX",          "production_orders/ga/2200/2026/prd_202602.xlsx"),
    ("production_orders/ga/2200/2026/GA_PRD_03.2026.XLSX",          "production_orders/ga/2200/2026/prd_202603.xlsx"),
    ("production_orders/ga/2200/2026/GA_PRD_04.2026.XLSX",          "production_orders/ga/2200/2026/prd_202604.xlsx"),
    ("production_orders/ga/2200/2026/PRD_2200_05.2026.XLSX",        "production_orders/ga/2200/2026/prd_202605.xlsx"),

    # ── SALES (VF05) ────────────────────────────────────────────────────────
    # AMC 2023
    ("sales/amc/2023/sale_2023_01.XLSX",   "sales/amc/2023/vf05_202301.xlsx"),
    ("sales/amc/2023/sale_2023_02.XLSX",   "sales/amc/2023/vf05_202302.xlsx"),
    ("sales/amc/2023/sale_2023_03.XLSX",   "sales/amc/2023/vf05_202303.xlsx"),
    ("sales/amc/2023/sale_2023_04.XLSX",   "sales/amc/2023/vf05_202304.xlsx"),
    ("sales/amc/2023/sale_2023_05.XLSX",   "sales/amc/2023/vf05_202305.xlsx"),
    ("sales/amc/2023/sale_2023_06.XLSX",   "sales/amc/2023/vf05_202306.xlsx"),
    ("sales/amc/2023/sale_2023_07.XLSX",   "sales/amc/2023/vf05_202307.xlsx"),
    ("sales/amc/2023/sale_2023_08.XLSX",   "sales/amc/2023/vf05_202308.xlsx"),
    ("sales/amc/2023/sale_2023_09.XLSX",   "sales/amc/2023/vf05_202309.xlsx"),
    ("sales/amc/2023/sale_2023_10.XLSX",   "sales/amc/2023/vf05_202310.xlsx"),
    ("sales/amc/2023/sale_2023_11.XLSX",   "sales/amc/2023/vf05_202311.xlsx"),
    ("sales/amc/2023/sale_2023_12.XLSX",   "sales/amc/2023/vf05_202312.xlsx"),
    # AMC 2024
    ("sales/amc/2024/sale_2024_01.XLSX",   "sales/amc/2024/vf05_202401.xlsx"),
    ("sales/amc/2024/sale_2024_02.XLSX",   "sales/amc/2024/vf05_202402.xlsx"),
    ("sales/amc/2024/sale_2024_03.XLSX",   "sales/amc/2024/vf05_202403.xlsx"),
    ("sales/amc/2024/sale_2024_04.XLSX",   "sales/amc/2024/vf05_202404.xlsx"),
    ("sales/amc/2024/sale_2024_05.XLSX",   "sales/amc/2024/vf05_202405.xlsx"),
    ("sales/amc/2024/sale_2024_06.XLSX",   "sales/amc/2024/vf05_202406.xlsx"),
    ("sales/amc/2024/sale_2024_07.XLSX",   "sales/amc/2024/vf05_202407.xlsx"),
    ("sales/amc/2024/sale_2024_08.XLSX",   "sales/amc/2024/vf05_202408.xlsx"),
    ("sales/amc/2024/sale_2024_09.XLSX",   "sales/amc/2024/vf05_202409.xlsx"),
    ("sales/amc/2024/sale_2024_10.XLSX",   "sales/amc/2024/vf05_202410.xlsx"),
    ("sales/amc/2024/sale_2024_11.XLSX",   "sales/amc/2024/vf05_202411.xlsx"),
    ("sales/amc/2024/sale_2024_12.XLSX",   "sales/amc/2024/vf05_202412.xlsx"),
    # AMC 2025
    ("sales/amc/2025/sale_2025_01.XLSX",   "sales/amc/2025/vf05_202501.xlsx"),
    ("sales/amc/2025/sale_2025_02.XLSX",   "sales/amc/2025/vf05_202502.xlsx"),
    ("sales/amc/2025/sale_2025_03.XLSX",   "sales/amc/2025/vf05_202503.xlsx"),
    ("sales/amc/2025/sale_2025_04.XLSX",   "sales/amc/2025/vf05_202504.xlsx"),
    ("sales/amc/2025/sale_2025_05.XLSX",   "sales/amc/2025/vf05_202505.xlsx"),
    ("sales/amc/2025/sale_2025_06.XLSX",   "sales/amc/2025/vf05_202506.xlsx"),
    ("sales/amc/2025/sale_2025_07.XLSX",   "sales/amc/2025/vf05_202507.xlsx"),
    ("sales/amc/2025/sale_2025_08.XLSX",   "sales/amc/2025/vf05_202508.xlsx"),
    ("sales/amc/2025/sale_2025_09.XLSX",   "sales/amc/2025/vf05_202509.xlsx"),
    ("sales/amc/2025/sale_2025_10.XLSX",   "sales/amc/2025/vf05_202510.xlsx"),
    ("sales/amc/2025/sale_2025_11.XLSX",   "sales/amc/2025/vf05_202511.xlsx"),
    ("sales/amc/2025/sale_2025_12.XLSX",   "sales/amc/2025/vf05_202512.xlsx"),
    # AMC 2026
    ("sales/amc/2026/sale_01.2026.XLSX",   "sales/amc/2026/vf05_202601.xlsx"),
    ("sales/amc/2026/sale_02.2026.XLSX",   "sales/amc/2026/vf05_202602.xlsx"),
    ("sales/amc/2026/sale_03.2026.XLSX",   "sales/amc/2026/vf05_202603.xlsx"),
    ("sales/amc/2026/sale_04.2026.XLSX",   "sales/amc/2026/vf05_202604.xlsx"),
    ("sales/amc/2026/sale_05.2026.XLSX",   "sales/amc/2026/vf05_202605.xlsx"),
    # GA
    ("sales/ga/2026/sale_05.2026.XLSX",    "sales/ga/2026/vf05_202605.xlsx"),

    # ── TB SNAPSHOTS (F.01) ─────────────────────────────────────────────────
    ("tb_snapshots/amc/2026/AMC_TB_01.2026.XLSX",  "tb_snapshots/amc/2026/tb_202601.xlsx"),
    ("tb_snapshots/amc/2026/AMC_TB_02.2026.XLSX",  "tb_snapshots/amc/2026/tb_202602.xlsx"),
    ("tb_snapshots/amc/2026/AMC_TB_03.2026.XLSX",  "tb_snapshots/amc/2026/tb_202603.xlsx"),
    ("tb_snapshots/amc/2026/AMC_TB_04.2026.XLSX",  "tb_snapshots/amc/2026/tb_202604.xlsx"),
    ("tb_snapshots/amc/2026/AMC_TB_05.2026.XLSX",  "tb_snapshots/amc/2026/tb_202605.xlsx"),
    ("tb_snapshots/ga/2026/GA_TB_01.2026.XLSX",    "tb_snapshots/ga/2026/tb_202601.xlsx"),
    ("tb_snapshots/ga/2026/GA_TB_02.2026.XLSX",    "tb_snapshots/ga/2026/tb_202602.xlsx"),
    ("tb_snapshots/ga/2026/GA_TB_03.2026.XLSX",    "tb_snapshots/ga/2026/tb_202603.xlsx"),
    ("tb_snapshots/ga/2026/GA_TB_04.2026.XLSX",    "tb_snapshots/ga/2026/tb_202604.xlsx"),

    # ── TEMPLATES ───────────────────────────────────────────────────────────
    ("templates/AMC Group_Q12025 CONSO_Leadshest to client.xlsx",   "templates/leadsheet_q1_2025_conso.xlsx"),
    ("templates/AMC Group_Q125 CONSO_Cashflow to client.xlsx",      "templates/cashflow_q1_2025_conso.xlsx"),
    ("templates/AMC Leadsheet YE25.xlsx",                           "templates/leadsheet_ye_2025.xlsx"),
    ("templates/AMC SAM Q1 25.xlsx",                                "templates/sam_q1_2025.xlsx"),
    ("templates/AMC_Analytic sales questions Q1'26 m.xlsx",          "templates/analytic_sales_q1_2026.xlsx"),
    ("templates/AMC_Q12025_Leadsheet STAT to client.xlsx",          "templates/leadsheet_q1_2025_stat.xlsx"),
    ("templates/AMC_Q12026_Leadsheet STAT to client_.xlsx",         "templates/leadsheet_q1_2026_stat.xlsx"),
    ("templates/AMC_Q125_SEPERATE_Cashflow to client.xlsx",         "templates/cashflow_q1_2025_sep.xlsx"),
    ("templates/AMC_Q2_2026_Leadsheet STAT to client.xlsx",         "templates/leadsheet_q2_2026_stat.xlsx"),

    # ── WAREHOUSE STOCK (MB52) ───────────────────────────────────────────────
    # AMC 2023 — plant in name since multiple plants per year folder
    ("warehouse_stock/amc/2023/1100_2023_01.XLSX",  "warehouse_stock/amc/2023/mb52_1100_202301.xlsx"),
    ("warehouse_stock/amc/2023/1100_2023_02.XLSX",  "warehouse_stock/amc/2023/mb52_1100_202302.xlsx"),
    ("warehouse_stock/amc/2023/1100_2023_03.XLSX",  "warehouse_stock/amc/2023/mb52_1100_202303.xlsx"),
    ("warehouse_stock/amc/2023/1100_2023_04.XLSX",  "warehouse_stock/amc/2023/mb52_1100_202304.xlsx"),
    ("warehouse_stock/amc/2023/1100_2023_05.XLSX",  "warehouse_stock/amc/2023/mb52_1100_202305.xlsx"),
    ("warehouse_stock/amc/2023/1100_2023_06.XLSX",  "warehouse_stock/amc/2023/mb52_1100_202306.xlsx"),
    ("warehouse_stock/amc/2023/1100_2023_07.XLSX",  "warehouse_stock/amc/2023/mb52_1100_202307.xlsx"),
    ("warehouse_stock/amc/2023/1100_2023_08.XLSX",  "warehouse_stock/amc/2023/mb52_1100_202308.xlsx"),
    ("warehouse_stock/amc/2023/1100_2023_09.XLSX",  "warehouse_stock/amc/2023/mb52_1100_202309.xlsx"),
    ("warehouse_stock/amc/2023/1100_2023_10.XLSX",  "warehouse_stock/amc/2023/mb52_1100_202310.xlsx"),
    ("warehouse_stock/amc/2023/1100_2023_11.XLSX",  "warehouse_stock/amc/2023/mb52_1100_202311.xlsx"),
    ("warehouse_stock/amc/2023/1100_2023_12.XLSX",  "warehouse_stock/amc/2023/mb52_1100_202312.xlsx"),
    ("warehouse_stock/amc/2023/1200_2023_01.XLSX",  "warehouse_stock/amc/2023/mb52_1200_202301.xlsx"),
    ("warehouse_stock/amc/2023/1200_2023_02.XLSX",  "warehouse_stock/amc/2023/mb52_1200_202302.xlsx"),
    ("warehouse_stock/amc/2023/1200_2023_03.XLSX",  "warehouse_stock/amc/2023/mb52_1200_202303.xlsx"),
    ("warehouse_stock/amc/2023/1200_2023_04.XLSX",  "warehouse_stock/amc/2023/mb52_1200_202304.xlsx"),
    ("warehouse_stock/amc/2023/1200_2023_05.XLSX",  "warehouse_stock/amc/2023/mb52_1200_202305.xlsx"),
    ("warehouse_stock/amc/2023/1200_2023_06.XLSX",  "warehouse_stock/amc/2023/mb52_1200_202306.xlsx"),
    ("warehouse_stock/amc/2023/1200_2023_07.XLSX",  "warehouse_stock/amc/2023/mb52_1200_202307.xlsx"),
    ("warehouse_stock/amc/2023/1200_2023_08.XLSX",  "warehouse_stock/amc/2023/mb52_1200_202308.xlsx"),
    ("warehouse_stock/amc/2023/1200_2023_09.XLSX",  "warehouse_stock/amc/2023/mb52_1200_202309.xlsx"),
    ("warehouse_stock/amc/2023/1200_2023_10.XLSX",  "warehouse_stock/amc/2023/mb52_1200_202310.xlsx"),
    ("warehouse_stock/amc/2023/1200_2023_11.XLSX",  "warehouse_stock/amc/2023/mb52_1200_202311.xlsx"),
    ("warehouse_stock/amc/2023/1200_2023_12.XLSX",  "warehouse_stock/amc/2023/mb52_1200_202312.xlsx"),
    # AMC 2024
    ("warehouse_stock/amc/2024/1100_2024_01.XLSX",  "warehouse_stock/amc/2024/mb52_1100_202401.xlsx"),
    ("warehouse_stock/amc/2024/1100_2024_02.XLSX",  "warehouse_stock/amc/2024/mb52_1100_202402.xlsx"),
    ("warehouse_stock/amc/2024/1100_2024_03.XLSX",  "warehouse_stock/amc/2024/mb52_1100_202403.xlsx"),
    ("warehouse_stock/amc/2024/1100_2024_04.XLSX",  "warehouse_stock/amc/2024/mb52_1100_202404.xlsx"),
    ("warehouse_stock/amc/2024/1100_2024_05.XLSX",  "warehouse_stock/amc/2024/mb52_1100_202405.xlsx"),
    ("warehouse_stock/amc/2024/1100_2024_06.XLSX",  "warehouse_stock/amc/2024/mb52_1100_202406.xlsx"),
    ("warehouse_stock/amc/2024/1100_2024_07.XLSX",  "warehouse_stock/amc/2024/mb52_1100_202407.xlsx"),
    ("warehouse_stock/amc/2024/1100_2024_08.XLSX",  "warehouse_stock/amc/2024/mb52_1100_202408.xlsx"),
    ("warehouse_stock/amc/2024/1100_2024_09.XLSX",  "warehouse_stock/amc/2024/mb52_1100_202409.xlsx"),
    ("warehouse_stock/amc/2024/1100_2024_10.XLSX",  "warehouse_stock/amc/2024/mb52_1100_202410.xlsx"),
    ("warehouse_stock/amc/2024/1100_2024_11.XLSX",  "warehouse_stock/amc/2024/mb52_1100_202411.xlsx"),
    ("warehouse_stock/amc/2024/1100_2024_12.XLSX",  "warehouse_stock/amc/2024/mb52_1100_202412.xlsx"),
    ("warehouse_stock/amc/2024/1200_2024_01.XLSX",  "warehouse_stock/amc/2024/mb52_1200_202401.xlsx"),
    ("warehouse_stock/amc/2024/1200_2024_02.XLSX",  "warehouse_stock/amc/2024/mb52_1200_202402.xlsx"),
    ("warehouse_stock/amc/2024/1200_2024_03.XLSX",  "warehouse_stock/amc/2024/mb52_1200_202403.xlsx"),
    ("warehouse_stock/amc/2024/1200_2024_04.XLSX",  "warehouse_stock/amc/2024/mb52_1200_202404.xlsx"),
    ("warehouse_stock/amc/2024/1200_2024_05.XLSX",  "warehouse_stock/amc/2024/mb52_1200_202405.xlsx"),
    ("warehouse_stock/amc/2024/1200_2024_06.XLSX",  "warehouse_stock/amc/2024/mb52_1200_202406.xlsx"),
    ("warehouse_stock/amc/2024/1200_2024_07.XLSX",  "warehouse_stock/amc/2024/mb52_1200_202407.xlsx"),
    ("warehouse_stock/amc/2024/1200_2024_08.XLSX",  "warehouse_stock/amc/2024/mb52_1200_202408.xlsx"),
    ("warehouse_stock/amc/2024/1200_2024_09.XLSX",  "warehouse_stock/amc/2024/mb52_1200_202409.xlsx"),
    ("warehouse_stock/amc/2024/1200_2024_10.XLSX",  "warehouse_stock/amc/2024/mb52_1200_202410.xlsx"),
    ("warehouse_stock/amc/2024/1200_2024_11.XLSX",  "warehouse_stock/amc/2024/mb52_1200_202411.xlsx"),
    ("warehouse_stock/amc/2024/1200_2024_12.XLSX",  "warehouse_stock/amc/2024/mb52_1200_202412.xlsx"),
    # AMC 2025
    ("warehouse_stock/amc/2025/1100_2025_01.XLSX",  "warehouse_stock/amc/2025/mb52_1100_202501.xlsx"),
    ("warehouse_stock/amc/2025/1100_2025_02.XLSX",  "warehouse_stock/amc/2025/mb52_1100_202502.xlsx"),
    ("warehouse_stock/amc/2025/1100_2025_03.XLSX",  "warehouse_stock/amc/2025/mb52_1100_202503.xlsx"),
    ("warehouse_stock/amc/2025/1100_2025_04.XLSX",  "warehouse_stock/amc/2025/mb52_1100_202504.xlsx"),
    ("warehouse_stock/amc/2025/1100_2025_05.XLSX",  "warehouse_stock/amc/2025/mb52_1100_202505.xlsx"),
    ("warehouse_stock/amc/2025/1100_2025_06.XLSX",  "warehouse_stock/amc/2025/mb52_1100_202506.xlsx"),
    ("warehouse_stock/amc/2025/1100_2025_07.XLSX",  "warehouse_stock/amc/2025/mb52_1100_202507.xlsx"),
    ("warehouse_stock/amc/2025/1100_2025_08.XLSX",  "warehouse_stock/amc/2025/mb52_1100_202508.xlsx"),
    ("warehouse_stock/amc/2025/1100_2025_09.XLSX",  "warehouse_stock/amc/2025/mb52_1100_202509.xlsx"),
    ("warehouse_stock/amc/2025/1100_2025_10.XLSX",  "warehouse_stock/amc/2025/mb52_1100_202510.xlsx"),
    ("warehouse_stock/amc/2025/1100_2025_11.XLSX",  "warehouse_stock/amc/2025/mb52_1100_202511.xlsx"),
    ("warehouse_stock/amc/2025/1100_2025_12.XLSX",  "warehouse_stock/amc/2025/mb52_1100_202512.xlsx"),
    ("warehouse_stock/amc/2025/1200_2025_01.XLSX",  "warehouse_stock/amc/2025/mb52_1200_202501.xlsx"),
    ("warehouse_stock/amc/2025/1200_2025_02.XLSX",  "warehouse_stock/amc/2025/mb52_1200_202502.xlsx"),
    ("warehouse_stock/amc/2025/1200_2025_03.XLSX",  "warehouse_stock/amc/2025/mb52_1200_202503.xlsx"),
    ("warehouse_stock/amc/2025/1200_2025_04.XLSX",  "warehouse_stock/amc/2025/mb52_1200_202504.xlsx"),
    ("warehouse_stock/amc/2025/1200_2025_05.XLSX",  "warehouse_stock/amc/2025/mb52_1200_202505.xlsx"),
    ("warehouse_stock/amc/2025/1200_2025_06.XLSX",  "warehouse_stock/amc/2025/mb52_1200_202506.xlsx"),
    ("warehouse_stock/amc/2025/1200_2025_07.XLSX",  "warehouse_stock/amc/2025/mb52_1200_202507.xlsx"),
    ("warehouse_stock/amc/2025/1200_2025_08.XLSX",  "warehouse_stock/amc/2025/mb52_1200_202508.xlsx"),
    ("warehouse_stock/amc/2025/1200_2025_09.XLSX",  "warehouse_stock/amc/2025/mb52_1200_202509.xlsx"),
    ("warehouse_stock/amc/2025/1200_2025_10.XLSX",  "warehouse_stock/amc/2025/mb52_1200_202510.xlsx"),
    ("warehouse_stock/amc/2025/1200_2025_11.XLSX",  "warehouse_stock/amc/2025/mb52_1200_202511.xlsx"),
    ("warehouse_stock/amc/2025/1200_2025_12.XLSX",  "warehouse_stock/amc/2025/mb52_1200_202512.xlsx"),
    ("warehouse_stock/amc/2025/1300_2025_07.XLSX",  "warehouse_stock/amc/2025/mb52_1300_202507.xlsx"),
    ("warehouse_stock/amc/2025/1300_2025_08.XLSX",  "warehouse_stock/amc/2025/mb52_1300_202508.xlsx"),
    ("warehouse_stock/amc/2025/1300_2025_09.XLSX",  "warehouse_stock/amc/2025/mb52_1300_202509.xlsx"),
    ("warehouse_stock/amc/2025/1300_2025_10.XLSX",  "warehouse_stock/amc/2025/mb52_1300_202510.xlsx"),
    ("warehouse_stock/amc/2025/1300_2025_11.XLSX",  "warehouse_stock/amc/2025/mb52_1300_202511.xlsx"),
    ("warehouse_stock/amc/2025/1300_2025_12.XLSX",  "warehouse_stock/amc/2025/mb52_1300_202512.xlsx"),
    # AMC 2026 — originally named with dots: 1100.01.2026.XLSX
    ("warehouse_stock/amc/2026/1100.01.2026.XLSX",  "warehouse_stock/amc/2026/mb52_1100_202601.xlsx"),
    ("warehouse_stock/amc/2026/1100.02.2026.XLSX",  "warehouse_stock/amc/2026/mb52_1100_202602.xlsx"),
    ("warehouse_stock/amc/2026/1100.03.2026.XLSX",  "warehouse_stock/amc/2026/mb52_1100_202603.xlsx"),
    ("warehouse_stock/amc/2026/1100.04.2026.XLSX",  "warehouse_stock/amc/2026/mb52_1100_202604.xlsx"),
    ("warehouse_stock/amc/2026/1100.05.2026.XLSX",  "warehouse_stock/amc/2026/mb52_1100_202605.xlsx"),
    ("warehouse_stock/amc/2026/1200.01.2026.XLSX",  "warehouse_stock/amc/2026/mb52_1200_202601.xlsx"),
    ("warehouse_stock/amc/2026/1200.02.2026.XLSX",  "warehouse_stock/amc/2026/mb52_1200_202602.xlsx"),
    ("warehouse_stock/amc/2026/1200.03.2026.XLSX",  "warehouse_stock/amc/2026/mb52_1200_202603.xlsx"),
    ("warehouse_stock/amc/2026/1200.04.2026.XLSX",  "warehouse_stock/amc/2026/mb52_1200_202604.xlsx"),
    ("warehouse_stock/amc/2026/1200.05.2026.XLSX",  "warehouse_stock/amc/2026/mb52_1200_202605.xlsx"),
    ("warehouse_stock/amc/2026/1300.01.2026.XLSX",  "warehouse_stock/amc/2026/mb52_1300_202601.xlsx"),
    ("warehouse_stock/amc/2026/1300.02.2026.XLSX",  "warehouse_stock/amc/2026/mb52_1300_202602.xlsx"),
    ("warehouse_stock/amc/2026/1300.03.2026.XLSX",  "warehouse_stock/amc/2026/mb52_1300_202603.xlsx"),
    ("warehouse_stock/amc/2026/1300.04.2026.XLSX",  "warehouse_stock/amc/2026/mb52_1300_202604.xlsx"),
    ("warehouse_stock/amc/2026/1300.05.2026.XLSX",  "warehouse_stock/amc/2026/mb52_1300_202605.xlsx"),
]

# ---------------------------------------------------------------------------
# DELETES: files to remove (duplicates, backups, superseded)
# ---------------------------------------------------------------------------
DELETES = [
    # AP: original superseded by _updated version
    "ap/amc/deposit_Q4'2025.xlsx",

    # Cost Center: typo duplicate (double underscore)
    "cost_center/amc/all/2026/KSB1__05.2026.XLSX",

    # GL: AMC_GL_* are duplicates of gl_2026_* (same data, different naming)
    "gl/amc/2026/AMC_GL_01.2026.XLSX",
    "gl/amc/2026/AMC_GL_02.2026.XLSX",
    "gl/amc/2026/AMC_GL_03.2026.XLSX",
    "gl/amc/2026/AMC_GL_04.2026.XLSX",
    "gl/amc/2026/AMC_GL_05.2026.XLSX",
    # GA: GA_GL_04 is duplicate of GA_2200_04
    "gl/ga/2026/GA_GL_04.2026.XLSX",

    # Inventory: sale_*.2026 are duplicates already in sales/amc/2026/
    "inventory/amc/sale_01.2026.XLSX",
    "inventory/amc/sale_02.2026.XLSX",
    "inventory/amc/sale_03.2026.XLSX",
    "inventory/amc/sale_04.2026.XLSX",
    # NRV v1 superseded by v2
    "inventory/amc/NRV_SKU_Analysis_2026_Q1.xlsx",

    # Payroll: backup file
    "payroll/amc/mapping/mapping_template_backup.xlsx",
]


def safe_rename(src: Path, dst: Path, dry_run: bool) -> str:
    """Rename src → dst. On Windows, uses two-step rename for case-only changes."""
    if not src.exists():
        return f"  SKIP (not found): {src.name}"
    # Use string comparison to be case-sensitive (Windows Path == is case-insensitive)
    src_s, dst_s = str(src), str(dst)
    # Truly identical string path (no rename needed)
    if src_s == dst_s:
        return f"  SKIP (already done): {src.name}"
    # Destination already exists at a DIFFERENT string path (collision)
    if dst.exists() and src_s != dst_s and src.name.lower() != dst.name.lower():
        return f"  SKIP (dst exists): {dst.name}"
    if dry_run:
        return f"  DRY  {src.name!r:70s} → {dst.name!r}"
    # Two-step rename for Windows case-insensitive filesystem (case-only change)
    if src.parent == dst.parent and src.name.lower() == dst.name.lower():
        tmp = src.parent / ("__tmp__" + src.name)
        os.rename(src, tmp)
        os.rename(tmp, dst)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.rename(src, dst)
    return f"  OK   {src.name!r:70s} → {dst.name!r}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without making changes")
    args = parser.parse_args()
    dry = args.dry_run

    print(f"{'DRY RUN — ' if dry else ''}Bronze rename: {ROOT}")
    print("=" * 80)

    # ── DELETES ──────────────────────────────────────────────────────────────
    deleted = skipped_del = 0
    print(f"\n[DELETE] {len(DELETES)} files")
    for rel in DELETES:
        p = ROOT / rel
        if not p.exists():
            print(f"  SKIP  (not found): {rel}")
            skipped_del += 1
        elif dry:
            print(f"  DRY   DELETE: {rel}")
        else:
            p.unlink()
            print(f"  DEL   {rel}")
            deleted += 1

    # ── RENAMES ──────────────────────────────────────────────────────────────
    renamed = skipped_ren = errors = 0
    print(f"\n[RENAME] {len(RENAMES)} files")
    for rel_src, rel_dst in RENAMES:
        src = ROOT / rel_src
        dst = ROOT / rel_dst
        result = safe_rename(src, dst, dry)
        print(result)
        if result.startswith("  OK"):
            renamed += 1
        elif result.startswith("  SKIP"):
            skipped_ren += 1
        elif result.startswith("  DRY"):
            renamed += 1  # count as would-rename

    print("\n" + "=" * 80)
    if dry:
        print(f"DRY RUN complete — would rename {renamed}, skip {skipped_ren}, delete {deleted + len(DELETES) - skipped_del}")
    else:
        print(f"Done — renamed {renamed}, skipped {skipped_ren}, deleted {deleted}, not-found {skipped_del}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
