"""Tools exposed to the lead agent for materializing final deliverables.

The lead agent (`orc`) reads worker text outputs and may then call any of
these tools to write a concrete file the user can open. Workers do not
call these tools — they only produce structured text. This keeps file
generation centralized and avoids parallel workers racing to write
duplicate documents.
"""

from tools.exports import create_docx, create_markdown, create_pptx, create_xlsx
from tools.management_ppt import create_management_ppt
from tools.product_detail import create_product_detail_page

__all__ = [
    "create_docx",
    "create_management_ppt",
    "create_markdown",
    "create_product_detail_page",
    "create_pptx",
    "create_xlsx",
]
