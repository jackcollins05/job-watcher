import pytest

from job_watcher.role import in_role


@pytest.mark.parametrize("title", [
    "Financial Analyst II", "Senior Financial Analyst", "Analyst, Finance",
    "Finance Analyst", "FP&A Analyst", "Senior FP&A Analyst", "FP & A Analyst",
    "Financial Planning & Analysis Analyst", "Analyst - Financial Planning and Analysis",
    "Treasury Analyst", "Credit Analyst", "Commercial Banking Analyst",
    "Corporate Banking Analyst", "Capital Markets Analyst", "Investment Banking Analyst",
    "Banking Analyst", "Financial Risk Analyst", "Credit Risk Analyst",
    "Market Risk Analyst", "Liquidity Risk Analyst", "Counterparty Risk Analyst",
    "Treasury Risk Analyst", "Banking Risk Analyst", "Capital Risk Analyst",
    "Investment Risk Analyst", "Analyst, Senior Finance", "Finance Senior II Analyst",
    "FINANCIAL ANALYST", "aNaLySt, fInAnCe", "Financial—Analyst", "Finance_Analyst",
])
def test_included(title):
    assert in_role(title)


@pytest.mark.parametrize("title", [
    "", "Data Analyst", "Business Analyst", "Marketing Analyst", "Supply Chain Analyst",
    "Operations Analyst", "HR Analyst", "Risk Analyst", "Operational Risk Analyst",
    "Cyber Risk Analyst", "Security Risk Analyst", "Clinical Risk Analyst",
    "Finance Manager", "FP&A Director", "Treasury Assistant", "Financial Analystics",
    "Financial Data Analyst", "Nonfinancial Analyst", "Analyst Programmer",
])
def test_excluded(title):
    assert not in_role(title)
