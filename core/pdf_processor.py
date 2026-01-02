"""
PDF processing for Qupled.
Extracts text, images, and LaTeX from exam PDFs.
Supports Mathpix and Vision LLM for math-heavy and scanned PDFs.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import fitz  # PyMuPDF

    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from PIL import Image  # noqa: F401

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    from pdf2image import convert_from_path

    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

# Vision LLM support
VISION_AVAILABLE = False
try:
    from models.llm_manager import LLMManager

    VISION_AVAILABLE = True
except ImportError:
    pass

# Mathpix OCR support
MATHPIX_AVAILABLE = False
try:
    from config import Config
    if Config.MATHPIX_APP_ID and Config.MATHPIX_APP_KEY:
        MATHPIX_AVAILABLE = True
except ImportError:
    pass


class VLMExtractionError(Exception):
    """Raised when VLM API call fails for exercise extraction."""
    pass


# System prompt for VLM
EXERCISE_EXTRACTION_SYSTEM = """You are an expert exam document analyzer. Your task is to accurately extract hierarchical exercise structures. Think step-by-step with user-provided decision trees. Analyze the document structure carefully before extracting."""

# Prompt for VLM-based exercise extraction (Pass 1: structure + text, no context)
EXERCISE_EXTRACTION_PROMPT = """Extract ALL exercises from these exam pages as a flat list.

DECISION TREE - Apply to each item:

Q1: "Does this start a NEW DISTINCT PROBLEM?"
→ YES: Main exercise (1, 2, 3...)
→ NO: Q2

Q2: "Does this GIVE INFORMATION to student (definitions, setup, given data)?"
→ YES: Part of parent text
→ NO: Q3

Q3: "Does this ask student to DO something (produce answer, calculation, drawing)?"
→ YES: Sub-question (1.1, 1.2...)
→ NO: Part of parent text

RULES:
- Parent text = FULL exercise block (intro + sub-questions + any text after)
- Sub-questions can be marked: a), b), c), 1., 2., i), ii), -, •, or unmarked
- NOT sub-questions: multiple choice options - treat as ONE exercise
- END BEFORE: form fields, blank lines for answers, solutions, page headers/footers, junk, exam instructions
- exercise_number: use hierarchical format (1, 1.1, 1.2) not document numbering
- page_number: 1-indexed
- image_context: describe visual elements; null if none
- Use LaTeX: $inline$ or $$block$$
- Ignore solution sections

Return valid JSON:
{
  "exercises": [
    {"exercise_number": "1", "text": "<full block>", "image_context": "<description or null>", "page_number": 1},
    {"exercise_number": "1.1", "text": "<sub-question>", "page_number": 1},
    {"exercise_number": "1.2", "text": "<sub-question>", "page_number": 1},
    {"exercise_number": "2", "text": "<standalone>", "image_context": "<description or null>", "page_number": 2}
  ]
}"""


# Prompt for DeepSeek context extraction (Pass 2)
CONTEXT_EXTRACTION_PROMPT_PARENT = """Extract the **shared context** that sub-questions need from this parent exercise.

**Good context**: data values, parameters, scenario setup, definitions that sub-questions reference.
Return **null** if sub-questions are **independent** and don't need shared info.
**IMPORTANT**: Return context_summary in **ENGLISH**, even if source is another language.

PARENT EXERCISE:
\"\"\"
{exercise_text}
\"\"\"

Return JSON:
{{"context_summary": "shared context in English" or null}}"""

CONTEXT_EXTRACTION_PROMPT_STANDALONE = """Summarize this exercise for context.

Focus on:
- The **core skill/concept** being tested
- Key **data values**, **parameters**, or given information
- What the student must **DO**

Keep it **concise**.
**IMPORTANT**: Return summary in **ENGLISH**, even if source is another language.

EXERCISE:
\"\"\"
{exercise_text}
\"\"\"

Return JSON:
{{"context_summary": "concise exercise summary in English" or null}}"""


@dataclass
class PDFPage:
    """Represents a single page from a PDF."""

    page_number: int
    text: str
    images: List[bytes]
    has_latex: bool
    latex_content: Optional[str] = None


@dataclass
class PDFContent:
    """Complete PDF content extraction."""

    file_path: Path
    total_pages: int
    pages: List[PDFPage]
    metadata: Dict[str, Any]


class PDFProcessor:
    """Processes PDF files to extract text, images, and formulas."""

    def __init__(self):
        """Initialize PDF processor."""
        if not PYMUPDF_AVAILABLE:
            raise ImportError("PyMuPDF is required. Install: pip install pymupdf")

    def process_pdf(self, pdf_path: Path) -> PDFContent:
        """Process a PDF file and extract all content.

        Args:
            pdf_path: Path to PDF file

        Returns:
            PDFContent with extracted information
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        return self._process_with_pymupdf(pdf_path)

    def _process_with_pymupdf(self, pdf_path: Path) -> PDFContent:
        """Process PDF using PyMuPDF (fitz).

        Args:
            pdf_path: Path to PDF file

        Returns:
            PDFContent with extracted information
        """
        doc = fitz.open(pdf_path)
        pages = []

        for page_num in range(len(doc)):
            page = doc[page_num]

            # Extract text
            text = page.get_text()

            # Extract images
            images = []
            image_list = page.get_images()
            for img_index, img in enumerate(image_list):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    images.append(image_bytes)
                except Exception:
                    # Skip problematic images
                    continue

            # Check for LaTeX (simple heuristic)
            has_latex, latex_content = self._detect_latex(text)

            pages.append(
                PDFPage(
                    page_number=page_num + 1,
                    text=text,
                    images=images,
                    has_latex=has_latex,
                    latex_content=latex_content,
                )
            )

        # Extract metadata
        metadata = doc.metadata or {}

        doc.close()

        return PDFContent(
            file_path=pdf_path, total_pages=len(pages), pages=pages, metadata=metadata
        )

    def _detect_latex(self, text: str) -> Tuple[bool, Optional[str]]:
        """Detect LaTeX formulas in text.

        Args:
            text: Text to analyze

        Returns:
            Tuple of (has_latex: bool, latex_content: str or None)
        """
        # Common LaTeX patterns
        latex_patterns = [
            r"\$.*?\$",  # Inline math $...$
            r"\$\$.*?\$\$",  # Display math $$...$$
            r"\\begin\{equation\}.*?\\end\{equation\}",
            r"\\begin\{align\}.*?\\end\{align\}",
            r"\\begin\{math\}.*?\\end\{math\}",
            r"\\frac\{.*?\}\{.*?\}",  # Fractions
            r"\\sum",
            r"\\int",
            r"\\prod",  # Math operators
            r"\\alpha",
            r"\\beta",
            r"\\gamma",  # Greek letters
        ]

        latex_content = []
        has_latex = False

        for pattern in latex_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            if matches:
                has_latex = True
                latex_content.extend(matches)

        if has_latex:
            return True, "\n".join(latex_content[:10])  # Limit to first 10 matches
        return False, None

    def extract_text_from_page(self, pdf_path: Path, page_number: int) -> str:
        """Extract text from a specific page.

        Args:
            pdf_path: Path to PDF file
            page_number: Page number (1-indexed)

        Returns:
            Extracted text
        """
        doc = fitz.open(pdf_path)
        page = doc[page_number - 1]
        text = page.get_text()
        doc.close()
        return text

    def extract_images_from_page(self, pdf_path: Path, page_number: int) -> List[bytes]:
        """Extract images from a specific page.

        Args:
            pdf_path: Path to PDF file
            page_number: Page number (1-indexed)

        Returns:
            List of image bytes
        """
        images = []
        doc = fitz.open(pdf_path)
        page = doc[page_number - 1]

        image_list = page.get_images()
        for img in image_list:
            try:
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                images.append(image_bytes)
            except Exception:
                continue

        doc.close()
        return images

    def get_pdf_page_count(self, pdf_path: Path) -> int:
        """Get the number of pages in a PDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Number of pages
        """
        doc = fitz.open(pdf_path)
        count = len(doc)
        doc.close()
        return count

    def is_scanned_pdf(self, pdf_path: Path, sample_pages: int = 3) -> bool:
        """Detect if PDF is scanned (image-based) or digital (text-based).

        Args:
            pdf_path: Path to PDF file
            sample_pages: Number of pages to sample

        Returns:
            True if PDF appears to be scanned (needs OCR)
        """
        total_pages = self.get_pdf_page_count(pdf_path)
        pages_to_check = min(sample_pages, total_pages)

        text_chars = 0
        for page_num in range(1, pages_to_check + 1):
            text = self.extract_text_from_page(pdf_path, page_num)
            text_chars += len(text.strip())

        # If very little text extracted, likely scanned
        avg_chars_per_page = text_chars / pages_to_check if pages_to_check > 0 else 0
        return avg_chars_per_page < 100  # Threshold: less than 100 chars/page = scanned

    def process_pdf_with_mathpix(self, pdf_path: Path) -> PDFContent:
        """Process PDF using Mathpix OCR for high-quality text + LaTeX extraction.

        Mathpix is specialized for math OCR and produces clean LaTeX output.

        Args:
            pdf_path: Path to PDF file

        Returns:
            PDFContent with Mathpix-extracted text

        Raises:
            ImportError: If Mathpix not configured
            FileNotFoundError: If PDF not found
        """
        if not MATHPIX_AVAILABLE:
            raise ImportError(
                "Mathpix not configured. Set MATHPIX_APP_ID and MATHPIX_APP_KEY."
            )

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        import time

        import requests

        # Read PDF file
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # Send to Mathpix API
        url = "https://api.mathpix.com/v3/pdf"
        headers = {
            "app_id": Config.MATHPIX_APP_ID,
            "app_key": Config.MATHPIX_APP_KEY,
        }

        # Upload PDF and start conversion
        response = requests.post(
            url,
            headers=headers,
            files={"file": (pdf_path.name, pdf_bytes, "application/pdf")},
            data={
                "options_json": '{"math_inline_delimiters": ["$", "$"], "math_display_delimiters": ["$$", "$$"]}'
            },
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        pdf_id = result.get("pdf_id")

        if not pdf_id:
            raise RuntimeError(f"Mathpix upload failed: {result}")

        # Poll for completion
        status_url = f"https://api.mathpix.com/v3/pdf/{pdf_id}"
        max_wait = 300  # 5 minutes max
        poll_interval = 2
        waited = 0

        while waited < max_wait:
            status_resp = requests.get(status_url, headers=headers, timeout=30)
            status_resp.raise_for_status()
            status = status_resp.json()

            if status.get("status") == "completed":
                break
            elif status.get("status") == "error":
                raise RuntimeError(f"Mathpix processing error: {status}")

            time.sleep(poll_interval)
            waited += poll_interval

        if waited >= max_wait:
            raise TimeoutError("Mathpix processing timed out")

        # Get the extracted text (mmd format = markdown with math)
        text_url = f"https://api.mathpix.com/v3/pdf/{pdf_id}.mmd"
        text_resp = requests.get(text_url, headers=headers, timeout=30)
        text_resp.raise_for_status()
        full_text = text_resp.text

        # Split by page markers if present, otherwise treat as single page
        # Mathpix uses \newpage or page markers
        page_texts = full_text.split("\\newpage") if "\\newpage" in full_text else [full_text]

        pages = []
        for page_num, page_text in enumerate(page_texts, start=1):
            page_text = page_text.strip()
            if not page_text:
                continue

            # Check for LaTeX patterns
            has_latex, latex_content = self._detect_latex(page_text)

            # Extract embedded images using pymupdf
            images = self.extract_images_from_page(pdf_path, page_num) if page_num <= self.get_pdf_page_count(pdf_path) else []

            pages.append(
                PDFPage(
                    page_number=page_num,
                    text=page_text,
                    images=images,
                    has_latex=has_latex,
                    latex_content=latex_content,
                )
            )

        # Get metadata using pymupdf
        doc = fitz.open(pdf_path)
        metadata = doc.metadata or {}
        total_pages = len(doc)
        doc.close()

        # If Mathpix returned fewer pages, pad with empty pages
        while len(pages) < total_pages:
            pages.append(
                PDFPage(
                    page_number=len(pages) + 1,
                    text="",
                    images=[],
                    has_latex=False,
                    latex_content=[],
                )
            )

        return PDFContent(
            file_path=pdf_path, total_pages=total_pages, pages=pages, metadata=metadata
        )

    def process_image_with_mathpix(self, image_path: Path) -> str:
        """Process a single image (PNG/JPG) using Mathpix OCR.

        Uses Mathpix /v3/text endpoint for high-quality math OCR from images.

        Args:
            image_path: Path to image file (PNG, JPG, JPEG)

        Returns:
            Extracted text with LaTeX formatting

        Raises:
            ImportError: If Mathpix not configured
            FileNotFoundError: If image not found
            ValueError: If unsupported image format
        """
        if not MATHPIX_AVAILABLE:
            raise ImportError(
                "Mathpix not configured. Set MATHPIX_APP_ID and MATHPIX_APP_KEY."
            )

        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # Validate file extension
        suffix = image_path.suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg"}:
            raise ValueError(f"Unsupported image format: {suffix}. Use PNG or JPG.")

        import base64

        import requests

        # Read and encode image
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        # Determine content type
        content_type = "image/png" if suffix == ".png" else "image/jpeg"
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:{content_type};base64,{image_b64}"

        # Send to Mathpix /v3/text API
        url = "https://api.mathpix.com/v3/text"
        headers = {
            "app_id": Config.MATHPIX_APP_ID,
            "app_key": Config.MATHPIX_APP_KEY,
            "Content-type": "application/json",
        }

        payload = {
            "src": data_uri,
            "formats": ["text", "latex_styled"],
            "math_inline_delimiters": ["$", "$"],
            "math_display_delimiters": ["$$", "$$"],
        }

        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()

        # Prefer latex_styled if available, otherwise use text
        text = result.get("latex_styled") or result.get("text", "")

        return text

    def process_file_with_mathpix(self, file_path: Path) -> str:
        """Process any supported file (PDF or image) using Mathpix.

        Routes to appropriate Mathpix endpoint based on file type:
        - PDF: Uses /v3/pdf (async polling)
        - Images: Uses /v3/text (sync)

        Args:
            file_path: Path to file (PDF, PNG, JPG)

        Returns:
            Extracted text with LaTeX formatting

        Raises:
            ImportError: If Mathpix not configured
            FileNotFoundError: If file not found
            ValueError: If unsupported file format
        """
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            # Use PDF endpoint - returns PDFContent, extract text from pages
            content = self.process_pdf_with_mathpix(file_path)
            return "\n\n".join(page.text for page in content.pages if page.text)
        elif suffix in {".png", ".jpg", ".jpeg"}:
            # Use image endpoint
            return self.process_image_with_mathpix(file_path)
        else:
            raise ValueError(
                f"Unsupported file format: {suffix}. Supported: PDF, PNG, JPG."
            )

    def process_pdf_with_vision(
        self,
        pdf_path: Path,
        llm_manager: "LLMManager" = None,
        dpi: int = 200,
    ) -> PDFContent:
        """Process PDF using Vision LLM for OCR with proper LaTeX extraction.

        This is the primary pipeline for math-heavy PDFs. Renders pages as
        images then uses DeepSeek Vision to extract text with proper LaTeX.

        Args:
            pdf_path: Path to PDF file
            llm_manager: LLMManager instance (defaults to DeepSeek)
            dpi: Resolution for rendering (200 is good balance of quality/speed)

        Returns:
            PDFContent with Vision-OCR extracted text

        Raises:
            ImportError: If pdf2image not installed
            FileNotFoundError: If PDF not found
        """
        if not PDF2IMAGE_AVAILABLE:
            raise ImportError(
                "pdf2image not available. Install: pip install pdf2image"
            )

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Create LLMManager if not provided
        if llm_manager is None:
            if not VISION_AVAILABLE:
                raise ImportError(
                    "LLMManager not available. Ensure models.llm_manager is importable."
                )
            llm_manager = LLMManager(provider="deepseek")

        # Render PDF pages as images
        page_images = convert_from_path(pdf_path, dpi=dpi)

        pages = []
        for page_num, img in enumerate(page_images, start=1):
            # Convert PIL Image to bytes for Vision API
            import io
            img_buffer = io.BytesIO()
            img.save(img_buffer, format="PNG")
            img_bytes = img_buffer.getvalue()

            # OCR using Vision LLM
            text = self._ocr_page_with_vision(img_bytes, llm_manager)

            # Extract embedded images using pymupdf
            images = self.extract_images_from_page(pdf_path, page_num)

            # Check for LaTeX patterns in OCR text
            has_latex, latex_content = self._detect_latex(text)

            pages.append(
                PDFPage(
                    page_number=page_num,
                    text=text,
                    images=images,
                    has_latex=has_latex,
                    latex_content=latex_content,
                )
            )

        # Get metadata using pymupdf
        doc = fitz.open(pdf_path)
        metadata = doc.metadata or {}
        doc.close()

        return PDFContent(
            file_path=pdf_path, total_pages=len(pages), pages=pages, metadata=metadata
        )

    def _ocr_page_with_vision(
        self,
        image_bytes: bytes,
        llm_manager: "LLMManager",
    ) -> str:
        """Extract text from PDF page image using Vision LLM.

        Args:
            image_bytes: PNG image data
            llm_manager: LLMManager with vision support

        Returns:
            Extracted text with proper LaTeX formatting
        """
        prompt = """Extract ALL text from this PDF page.

CRITICAL for math notation:
- Use proper LaTeX for equations: $...$ inline, $$...$$ block
- Matrices: $$\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$$
- Vectors: $\\vec{v}$ or $(x, y, z)$
- Fractions: $\\frac{a}{b}$
- Greek letters: $\\alpha$, $\\beta$, $\\gamma$, etc.
- Subscripts: $x_1$, superscripts: $x^2$
- Preserve exercise numbering (1., 2., a), b), i), ii), etc.)

Output the text with proper formatting. Preserve paragraph structure."""

        response = llm_manager.generate_with_image(
            prompt=prompt,
            image_bytes=image_bytes,
            max_tokens=4000,
            temperature=0.1,  # Low temperature for accurate extraction
        )

        if response.success:
            return response.text
        else:
            # Log error but return empty string to continue processing
            import logging
            logging.getLogger(__name__).warning(
                f"Vision OCR failed: {response.error}"
            )
            return ""

    def describe_image(
        self,
        image_bytes: bytes,
        llm_manager: "LLMManager" = None,
    ) -> str:
        """Get text description of an image for exercise context.

        Used to generate image_context for exercises with diagrams.

        Args:
            image_bytes: Image data (PNG, JPEG)
            llm_manager: LLMManager instance (defaults to DeepSeek)

        Returns:
            Text description of the image content
        """
        if llm_manager is None:
            if not VISION_AVAILABLE:
                return ""
            llm_manager = LLMManager(provider="deepseek")

        prompt = """Describe this image for a student studying. Include:
- What it shows (diagram type, components)
- Any labels, text, or annotations visible
- Key values or measurements
- Relationships between elements

Be concise but complete. Focus on information needed to understand the exercise."""

        response = llm_manager.generate_with_image(
            prompt=prompt,
            image_bytes=image_bytes,
            max_tokens=500,
            temperature=0.3,
        )

        if response.success:
            return response.text
        return ""

    def extract_images_with_context(
        self,
        pdf_path: Path,
        page_number: int,
        llm_manager: "LLMManager" = None,
        min_size: int = 50,
        max_page_ratio: float = 0.8,
    ) -> List[Dict[str, Any]]:
        """Extract images from page with Vision LLM descriptions.

        Filters out noise (icons, backgrounds) and describes meaningful images.

        Args:
            pdf_path: Path to PDF file
            page_number: Page number (1-indexed)
            llm_manager: LLMManager instance
            min_size: Minimum image dimension (pixels)
            max_page_ratio: Maximum ratio of page size (filter backgrounds)

        Returns:
            List of dicts with 'bytes', 'position', 'description' keys
        """
        doc = fitz.open(pdf_path)
        page = doc[page_number - 1]
        page_rect = page.rect

        results = []
        image_list = page.get_images()

        for img in image_list:
            try:
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                width = base_image.get("width", 0)
                height = base_image.get("height", 0)

                # Filter: too small (icons, bullets)
                if width < min_size or height < min_size:
                    continue

                # Filter: too large (backgrounds)
                page_width = page_rect.width
                page_height = page_rect.height
                if width > page_width * max_page_ratio and height > page_height * max_page_ratio:
                    continue

                # Get image position on page
                img_rects = page.get_image_rects(xref)
                position = None
                if img_rects:
                    rect = img_rects[0]
                    position = {
                        "x": rect.x0,
                        "y": rect.y0,
                        "width": rect.width,
                        "height": rect.height,
                    }

                # Get description using Vision LLM
                description = ""
                if llm_manager:
                    description = self.describe_image(image_bytes, llm_manager)

                results.append({
                    "bytes": image_bytes,
                    "position": position,
                    "description": description,
                    "width": width,
                    "height": height,
                })

            except Exception:
                continue

        doc.close()
        return results


def render_page_to_image(pdf_path: Path, page_num: int, dpi: int = 150) -> bytes:
    """Render a single PDF page to PNG image bytes.

    Args:
        pdf_path: Path to PDF file
        page_num: Page number (1-indexed)
        dpi: Resolution for rendering (150 is good balance of quality/size)

    Returns:
        PNG image bytes

    Raises:
        ImportError: If pdf2image not installed
        FileNotFoundError: If PDF not found
        ValueError: If page_num out of range
    """
    if not PDF2IMAGE_AVAILABLE:
        raise ImportError("pdf2image not available. Install: pip install pdf2image")

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    import io

    images = convert_from_path(
        pdf_path,
        first_page=page_num,
        last_page=page_num,
        dpi=dpi,
    )

    if not images:
        raise ValueError(f"Page {page_num} not found in PDF")

    buf = io.BytesIO()
    images[0].save(buf, format="PNG")
    return buf.getvalue()


def _get_context_summaries(
    parent_data: Dict[str, Dict[str, Any]],
    standalone_exercises: List[Dict[str, Any]],
    logger,
) -> Dict[str, Optional[str]]:
    """Pass 2: Get context summaries from DeepSeek for parents and standalone exercises.

    Args:
        parent_data: Dict of parent_num -> {text, image_context}
        standalone_exercises: List of standalone exercise dicts
        logger: Logger instance

    Returns:
        Dict of exercise_number -> context_summary (or None)
    """
    import json
    import re

    import requests

    api_key = Config.OPENROUTER_API_KEY
    if not api_key:
        logger.warning("OPENROUTER_API_KEY not configured, skipping context extraction")
        return {}

    # Use DeepSeek for context extraction
    model = "deepseek/deepseek-chat-v3-0324"

    results = {}

    # Process parents
    for parent_num, data in parent_data.items():
        prompt = CONTEXT_EXTRACTION_PROMPT_PARENT.format(exercise_text=data["text"])
        context = _call_deepseek_for_context(api_key, model, prompt, logger)
        results[parent_num] = context

    # Process standalone exercises
    for ex in standalone_exercises:
        prompt = CONTEXT_EXTRACTION_PROMPT_STANDALONE.format(exercise_text=ex["text"])
        context = _call_deepseek_for_context(api_key, model, prompt, logger)
        results[ex["exercise_number"]] = context

    parent_count = len(parent_data)
    standalone_count = len(standalone_exercises)
    null_count = sum(1 for v in results.values() if v is None)
    logger.info(
        f"DeepSeek Pass 2: {parent_count} parents, {standalone_count} standalone, "
        f"{null_count} returned null"
    )

    return results


def _call_deepseek_for_context(
    api_key: str,
    model: str,
    prompt: str,
    logger,
) -> Optional[str]:
    """Call DeepSeek API for context extraction."""
    import json
    import re

    import requests

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 500,
            },
            timeout=30,
        )
        response.raise_for_status()

        result = response.json()
        text = result["choices"][0]["message"]["content"]

        # Parse JSON response
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            data = json.loads(json_match.group())
            summary = data.get("context_summary")
            if summary and summary != "null":
                return summary

    except Exception as e:
        logger.warning(f"DeepSeek context extraction failed: {e}")

    return None


def extract_exercises(
    images: bytes | Path | List[bytes],
    llm_manager: "LLMManager" = None,
) -> List[Dict[str, Any]]:
    """Extract exercises from exam page(s) using VLM.

    This is the unified extraction function that does OCR, exercise splitting,
    and context extraction in a single VLM call.

    Args:
        images: Single image (bytes or Path) or list of page images (bytes)
        llm_manager: LLMManager instance (defaults to OpenRouter with VLM model)

    Returns:
        List of exercise dicts with fields:
        - exercise_number: str ("1", "1.1", "2", etc.)
        - text: str (exercise content with LaTeX)
        - page_number: int (1-indexed)
        - image_context: str | None (diagram description)
        - exercise_context: str | None (context for sub-questions)

    Raises:
        VLMExtractionError: API failure, invalid JSON response, etc.

    Example:
        >>> # Single image file
        >>> exercises = extract_exercises(Path("exam.png"))
        >>> # PDF pages rendered to images
        >>> page_images = [render_page_to_image(pdf, p) for p in range(1, 4)]
        >>> exercises = extract_exercises(page_images)
    """
    import base64
    import io
    import json
    import logging

    import requests

    logger = logging.getLogger(__name__)

    # Normalize input to list of bytes
    if isinstance(images, Path):
        # Single file path - read it
        if not images.exists():
            raise VLMExtractionError(f"File not found: {images}")
        with open(images, "rb") as f:
            image_list = [f.read()]
    elif isinstance(images, bytes):
        # Single image bytes
        image_list = [images]
    elif isinstance(images, list):
        # List of image bytes
        image_list = images
    else:
        raise VLMExtractionError(f"Invalid images type: {type(images)}")

    if not image_list:
        return []

    # Resize large images to max 2048px to reduce API costs
    resized_images = []
    for img_bytes in image_list:
        resized = _resize_image_if_needed(img_bytes, max_size=2048)
        resized_images.append(resized)

    # Build multi-image content for OpenRouter API
    content = [{"type": "text", "text": EXERCISE_EXTRACTION_PROMPT}]
    for img_bytes in resized_images:
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })

    # Call OpenRouter API
    api_key = Config.OPENROUTER_API_KEY
    if not api_key:
        raise VLMExtractionError("OPENROUTER_API_KEY not configured")

    model = Config.OPENROUTER_VLM_MODEL

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": EXERCISE_EXTRACTION_SYSTEM},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.1,
                "max_tokens": 8000,
            },
            timeout=120,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise VLMExtractionError(f"API call failed: {e}")

    result = response.json()

    # Extract text from response
    try:
        text = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise VLMExtractionError(f"Unexpected API response format: {e}")

    # Parse JSON from response (may be wrapped in markdown code block)
    text = text.strip()
    if text.startswith("```"):
        # Remove markdown code block
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON from VLM: {text[:500]}...")
        raise VLMExtractionError(f"Invalid JSON response: {e}")

    exercises = data.get("exercises", [])

    # Parse all exercises (VLM now outputs text for all)
    all_exercises = []
    for ex in exercises:
        if not isinstance(ex, dict):
            continue
        if "exercise_number" not in ex or "text" not in ex:
            continue

        all_exercises.append({
            "exercise_number": str(ex["exercise_number"]),
            "text": str(ex["text"]),
            "page_number": int(ex.get("page_number", 1)),
            "image_context": ex.get("image_context"),
        })

    logger.info(f"VLM Pass 1: extracted {len(all_exercises)} exercises from {len(image_list)} page(s)")

    # Identify parents (exercises that have sub-questions)
    # Use rsplit to find immediate parent: "3.1.1" → "3.1", "3.1" → "3"
    exercise_nums = {ex["exercise_number"] for ex in all_exercises}
    parent_nums = set()
    for ex_num in exercise_nums:
        if "." in ex_num:
            parent_num = ex_num.rsplit(".", 1)[0]
            if parent_num in exercise_nums:
                parent_nums.add(parent_num)

    # Pass 2: Get context from DeepSeek for parents and standalone
    parent_data = {}  # parent_num -> {text, image_context, context_summary}
    standalone_exercises = []

    for ex in all_exercises:
        ex_num = ex["exercise_number"]
        if ex_num in parent_nums:
            # Parent exercise - store for context extraction
            parent_data[ex_num] = {
                "text": ex["text"],
                "image_context": ex.get("image_context"),
            }
        elif "." not in ex_num:
            # Standalone exercise (no subs)
            standalone_exercises.append(ex)

    # Call DeepSeek for context (parents + standalone)
    if parent_data or standalone_exercises:
        context_results = _get_context_summaries(
            parent_data, standalone_exercises, logger
        )
    else:
        context_results = {}

    # Build final exercise list (subs only, with inherited context)
    final_exercises = []
    for ex in all_exercises:
        ex_num = ex["exercise_number"]

        if ex_num in parent_nums:
            # Skip parent entries - context is inherited by subs
            continue

        if "." in ex_num:
            # Sub-question - inherit context from immediate parent
            parent_num = ex_num.rsplit(".", 1)[0]
            parent = parent_data.get(parent_num, {})
            ex["exercise_context"] = context_results.get(parent_num)
            if ex.get("image_context") is None:
                ex["image_context"] = parent.get("image_context")
        else:
            # Standalone - use its own context
            ex["exercise_context"] = context_results.get(ex_num)

        final_exercises.append(ex)

    logger.info(f"Two-pass extraction complete: {len(final_exercises)} exercises")
    return final_exercises


def _resize_image_if_needed(image_bytes: bytes, max_size: int = 2048) -> bytes:
    """Resize image if either dimension exceeds max_size.

    Args:
        image_bytes: Original image bytes
        max_size: Maximum dimension (pixels)

    Returns:
        Resized image bytes (or original if no resize needed)
    """
    if not PIL_AVAILABLE:
        return image_bytes  # Can't resize without PIL

    import io

    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes))
    width, height = img.size

    if width <= max_size and height <= max_size:
        return image_bytes  # No resize needed

    # Calculate new size maintaining aspect ratio
    if width > height:
        new_width = max_size
        new_height = int(height * max_size / width)
    else:
        new_height = max_size
        new_width = int(width * max_size / height)

    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Save to bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
