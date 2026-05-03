"""PDF resume parser.

Extracts tech skills from Laiya_Wang_AWS.pdf by matching a master vocabulary
against the resume text. resume_scorer.py calls this at module load and uses
the result to auto-update the skill matching list whenever the PDF changes.

Falls back gracefully if pdfplumber is not installed or the PDF is unreadable.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

_PDF_PATH = Path(__file__).resolve().parents[2] / "Laiya_Wang_AWS.pdf"

# Master vocabulary of all tech skills we can detect.
# Entries not found in the resume text are excluded from scoring — so the
# scorer automatically narrows to Laiya's actual stack without manual edits.
# (pattern, weight, display_name)
# weight 3 = core tools she uses daily, 2 = strong supporting, 1 = familiar
_MASTER_SKILLS: List[Tuple[str, int, str]] = [
    # Core languages
    (r'(?<!\w)c#(?!\w)|c\s*sharp\b',                  3, "C#"),
    (r'\.net\b|dotnet\b|asp\.net\b',                 3, ".NET"),
    (r'\bpython\b',                                  3, "Python"),
    (r'\btypescript\b',                              3, "TypeScript"),
    (r'\breact\b',                                   3, "React"),
    (r'\bsql\b',                                     3, "SQL"),
    (r'\baws\b|amazon\s+web\s+services\b',            3, "AWS"),
    # Strong tools
    (r'\bazure\b',                                   2, "Azure"),
    (r'\bdocker\b',                                  2, "Docker"),
    (r'\bci[/\s\-]?cd\b|continuous\s+integration\b', 2, "CI/CD"),
    (r'\bdevops\b|dev\s*ops\b',                      2, "DevOps"),
    (r'\bnode\.?js\b|nodejs\b',                      2, "Node.js"),
    (r'\brest\s*(?:ful\s*)?api\b',                   2, "REST API"),
    (r'\bmicroservice',                              2, "Microservices"),
    (r'\bintegration\b',                             2, "Integration"),
    (r'\bkubernetes\b|\bk8s\b',                      2, "Kubernetes"),
    (r'\bpower\s+automate\b',                        2, "Power Automate"),
    (r'\boracle\b',                                  2, "Oracle"),
    (r'\bn8n\b',                                     2, "n8n"),
    (r'\bjava\b',                                    2, "Java"),
    (r'\bterraform\b',                               2, "Terraform"),
    (r'\bansible\b',                                 2, "Ansible"),
    (r'\bnginx\b',                                   2, "Nginx"),
    (r'\bapache\b',                                  2, "Apache"),
    (r'\bdynamodb\b',                                2, "DynamoDB"),
    (r'\blambda\b',                                  2, "AWS Lambda"),
    (r'\bvue\.?js\b|vuejs\b',                        2, "Vue.js"),
    (r'\bangular\b',                                 2, "Angular"),
    (r'\bflask\b|\bdjango\b|\bfastapi\b',            2, "Python Web"),
    (r'\bnext\.?js\b',                               2, "Next.js"),
    (r'\bspark\b',                                   2, "Spark"),
    (r'\bkafka\b',                                   2, "Kafka"),
    (r'\bgo\b|\bgolang\b',                           2, "Go"),
    (r'\brust\b',                                    2, "Rust"),
    (r'\bspring\b|\bspring\s+boot\b',                2, "Spring Boot"),
    # Familiar / transferable
    (r'\bgit\b|github\b|gitlab\b',                   1, "Git"),
    (r'\blinux\b|ubuntu\b|debian\b',                 1, "Linux"),
    (r'\bagile\b|\bscrum\b',                         1, "Agile"),
    (r'\bjavascript\b|\bjs\b',                       1, "JavaScript"),
    (r'\bcloud\b',                                   1, "Cloud"),
    (r'\bpostgres(?:ql)?\b',                         1, "PostgreSQL"),
    (r'\bhadoop\b',                                  1, "Hadoop"),
    (r'\belasticsearch\b',                           1, "Elasticsearch"),
    (r'\bredis\b',                                   1, "Redis"),
    (r'\bmongodb\b',                                 1, "MongoDB"),
    (r'\bpower\s+bi\b',                              1, "Power BI"),
    (r'\btableau\b',                                 1, "Tableau"),
    (r'\buml\b',                                     1, "UML"),
    (r'\bhtml\b',                                    1, "HTML"),
    (r'\bcss\b',                                     1, "CSS"),
    (r'\br\b',                                       1, "R"),
    (r'\bmatlab\b',                                  1, "MATLAB"),
    (r'\bjira\b',                                    1, "Jira"),
    (r'\bconfluence\b',                              1, "Confluence"),
    (r'\bapi\b',                                     1, "API"),
    (r'\bdns\b',                                     1, "DNS"),
    (r'\bssl\b|\btls\b',                             1, "SSL/TLS"),
    (r'\bkotlin\b',                                  1, "Kotlin"),
    (r'\bswift\b',                                   1, "Swift"),
]


def extract_skills_from_pdf(
    pdf_path: Path = _PDF_PATH,
) -> Optional[List[Tuple[str, int, str]]]:
    """Parse resume PDF and return (pattern, weight, name) tuples for found skills.

    Returns None if pdfplumber is unavailable or the PDF can't be read —
    callers should fall back to a hardcoded list.
    """
    try:
        import pdfplumber  # optional dependency
    except ImportError:
        return None

    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = " ".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        return None

    if len(text.strip()) < 50:
        return None

    found = [
        (pattern, weight, name)
        for pattern, weight, name in _MASTER_SKILLS
        if re.search(pattern, text, re.I)
    ]
    return found or None
