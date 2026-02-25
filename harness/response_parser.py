"""
Response parser: extract strategy_card.json and strategy.py from raw LLM output.
"""
import re
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class ResponseParser:
    """Extract structured artifacts from LLM response text."""

    def parse_response(self, response: str, output_dir: Path) -> Tuple[bool, str]:
        """
        Parse LLM response and save strategy_card.json + code/strategy.py.

        Args:
            response:   raw model output
            output_dir: directory where artifacts are written

        Returns:
            (success, error_message)
        """
        try:
            strategy_card = self._extract_json_block(response, "strategy_card")
            if not strategy_card:
                return False, "No strategy_card.json found in response"

            strategy_card_path = output_dir / "strategy_card.json"
            with open(strategy_card_path, 'w', encoding='utf-8') as f:
                json.dump(strategy_card, f, indent=2, ensure_ascii=False)
            logger.info("Saved strategy_card.json")

            code_blocks = self._extract_code_blocks(response)
            if not code_blocks:
                return False, "No code blocks found in response"

            code_dir = output_dir / "code"
            code_dir.mkdir(exist_ok=True)
            for filename, content in code_blocks.items():
                with open(code_dir / filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info(f"Saved {filename}")

            if not (code_dir / "strategy.py").exists():
                python_files = list(code_dir.glob("*.py"))
                if python_files:
                    python_files[0].rename(code_dir / "strategy.py")
                    logger.info(f"Renamed {python_files[0].name} to strategy.py")
                else:
                    return False, "No strategy.py or Python file found"

            logger.info(f"Successfully parsed response: {len(code_blocks)} files extracted")
            return True, ""

        except Exception as e:
            logger.error(f"Failed to parse response: {e}", exc_info=True)
            return False, f"Parse error: {str(e)}"

    def _extract_json_block(self, text: str, hint: str = None) -> Optional[Dict]:
        """Extract the first JSON block matching the optional hint keyword."""
        patterns = [
            r'```json\s*\n(.*?)\n```',
            r'```JSON\s*\n(.*?)\n```',
            r'```\s*\n(\{.*?\})\s*\n```',
        ]
        for pattern in patterns:
            for match in re.findall(pattern, text, re.DOTALL | re.IGNORECASE):
                try:
                    obj = json.loads(match)
                    if hint:
                        idx = text.find(match)
                        if hint.lower() in text[max(0, idx-200):idx].lower():
                            return obj
                    if 'strategy_id' in obj or 'strategy_name' in obj:
                        return obj
                except json.JSONDecodeError:
                    continue

        # Fallback: scan raw braces
        depth, start = 0, -1
        for i, char in enumerate(text):
            if char == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0 and start != -1:
                    try:
                        obj = json.loads(text[start:i+1])
                        if 'strategy_id' in obj or 'strategy_name' in obj:
                            return obj
                    except json.JSONDecodeError:
                        pass
                    start = -1
        return None

    def _extract_code_blocks(self, text: str) -> Dict[str, str]:
        """Extract all Python code blocks from response text."""
        code_blocks = {}
        patterns = [
            (r'```python:([^\s]+)\s*\n(.*?)\n```', True),
            (r'#\s*([^\s]+\.py)\s*\n```python\s*\n(.*?)\n```', True),
            (r'```python\s*\n(.*?)\n```', False),
            (r'```py\s*\n(.*?)\n```', False),
        ]
        for pattern, has_filename in patterns:
            for match in re.findall(pattern, text, re.DOTALL | re.IGNORECASE):
                if has_filename:
                    filename, content = match
                    code_blocks[filename.strip()] = content.strip()
                else:
                    content = match
                    if 'strategy.py' not in code_blocks:
                        code_blocks['strategy.py'] = content.strip()
        return code_blocks

    def validate_extraction(self, output_dir: Path) -> Tuple[bool, List[str]]:
        """Validate that required artifacts exist and are well-formed."""
        errors = []
        strategy_card_path = output_dir / "strategy_card.json"
        if not strategy_card_path.exists():
            errors.append("strategy_card.json not found")
        else:
            try:
                with open(strategy_card_path, 'r', encoding='utf-8') as f:
                    card = json.load(f)
                for field in ['strategy_id', 'strategy_name', 'parameters']:
                    if field not in card:
                        errors.append(f"Missing required field in strategy_card: {field}")
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON in strategy_card: {e}")

        code_dir = output_dir / "code"
        if not code_dir.exists():
            errors.append("code/ directory not found")
        else:
            if not list(code_dir.glob("*.py")):
                errors.append("No Python files found in code/")
            if not (code_dir / "strategy.py").exists():
                errors.append("strategy.py not found")

        return len(errors) == 0, errors


class ResponseParserV2:
    """Enhanced parser with fallback strategies for malformed responses."""

    def __init__(self):
        self.base_parser = ResponseParser()

    def parse_with_fallback(self, response: str, output_dir: Path) -> Tuple[bool, str]:
        """
        Parse response using multiple strategies:
          1. Standard (```json + ```python)
          2. Loose scan for any JSON + Python
        """
        success, error = self.base_parser.parse_response(response, output_dir)
        if success:
            return True, ""

        logger.warning(f"Standard parsing failed: {error}. Trying fallback...")
        try:
            json_objects = self._extract_all_json(response)
            strategy_card = next(
                (o for o in json_objects if 'strategy_id' in o or 'strategy_name' in o), None
            )
            if strategy_card:
                with open(output_dir / "strategy_card.json", 'w', encoding='utf-8') as f:
                    json.dump(strategy_card, f, indent=2, ensure_ascii=False)
                logger.info("Extracted strategy_card using fallback")

            python_code = self._extract_all_python(response)
            if python_code:
                code_dir = output_dir / "code"
                code_dir.mkdir(exist_ok=True)
                with open(code_dir / "strategy.py", 'w', encoding='utf-8') as f:
                    f.write(python_code)
                logger.info("Extracted Python code using fallback")

            is_valid, errors = self.base_parser.validate_extraction(output_dir)
            if is_valid:
                return True, "Parsed using fallback strategy"
            return False, f"Fallback failed: {'; '.join(errors)}"

        except Exception as e:
            return False, f"All parsing strategies failed: {str(e)}"

    def _extract_all_json(self, text: str) -> List[Dict]:
        objects, depth, start = [], 0, -1
        for i, char in enumerate(text):
            if char == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0 and start != -1:
                    try:
                        objects.append(json.loads(text[start:i+1]))
                    except json.JSONDecodeError:
                        pass
                    start = -1
        return objects

    def _extract_all_python(self, text: str) -> str:
        patterns = [r'```python\s*\n(.*?)\n```', r'```py\s*\n(.*?)\n```']
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            if matches:
                return matches[0].strip()
        return ""
