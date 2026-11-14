"""Only the three platforms supported by the saved audit."""

from .base import AdapterError
from .jibe import JibeAdapter
from .oracle import OracleAdapter
from .workday import WorkdayAdapter


def adapter_for(source):
    adapters = {"Workday CXS": WorkdayAdapter, "Oracle Recruiting CE": OracleAdapter,
                "iCIMS / Jibe": JibeAdapter}
    try:
        return adapters[source.platform]()
    except KeyError as exc:
        raise AdapterError(f"unsupported platform: {source.platform}") from exc
