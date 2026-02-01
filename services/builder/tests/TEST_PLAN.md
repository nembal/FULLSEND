# Builder Test Plan

This document describes the test plan for verifying Builder functionality.
Based on the PRD test plan in `docs/prd/PRD_BUILDER.md`.

## Overview

Builder must be tested with two scenarios:
1. **Simple Tool** - A basic hello_world tool with defaults
2. **Complex Tool** - A website_scraper requiring external libraries

---

## Test 1: Simple Tool (hello_world)

### PRD Setup

```bash
cat > services/builder/requests/current_prd.yaml << 'EOF'
prd:
  name: hello_world
  description: "A simple test tool"
  inputs:
    - name: name
      type: string
      default: "World"
  outputs:
    - name: greeting
      type: string
  requirements:
    - Return a greeting string
EOF
```

### Run Builder

```bash
./services/builder/run.sh
```

### Verification Steps

1. **Tool File Created:**
   ```bash
   test -f tools/hello_world.py && echo "PASS: Tool file exists" || echo "FAIL: Tool file missing"
   ```

2. **Tool Imports:**
   ```bash
   python -c "from tools.hello_world import hello_world; print('PASS: Import works')"
   ```

3. **Tool Runs:**
   ```bash
   python -c "
   from tools.hello_world import hello_world
   result = hello_world()
   print(f'PASS: Tool runs, result={result}')
   "
   ```

4. **Contract Compliance:**
   ```bash
   python -c "
   from tools.hello_world import hello_world
   result = hello_world()
   assert isinstance(result, dict), 'Result must be dict'
   assert 'result' in result, 'Missing result key'
   assert 'success' in result, 'Missing success key'
   assert 'error' in result, 'Missing error key'
   print('PASS: Contract compliance verified')
   "
   ```

5. **Run Alias Exists:**
   ```bash
   python -c "
   from tools.hello_world import run
   result = run(name='Test')
   print(f'PASS: run alias works, result={result}')
   "
   ```

6. **Git Commit Exists:**
   ```bash
   git log --oneline -1 tools/hello_world.py 2>/dev/null && echo "PASS: Committed" || echo "FAIL: Not committed"
   ```

7. **Redis Registration (if Redis available):**
   ```bash
   redis-cli HGETALL tools:hello_world 2>/dev/null && echo "PASS: Redis registered" || echo "SKIP: Redis not available"
   ```

### Expected Output

Builder should output **BUILD_COMPLETE** with:
- Tool name: hello_world
- File path: tools/hello_world.py
- Test results: PASSED

---

## Test 2: Complex Tool (website_scraper)

### PRD Setup

```bash
cat > services/builder/requests/current_prd.yaml << 'EOF'
prd:
  name: website_scraper
  description: "Scrape text content from a website"
  inputs:
    - name: url
      type: string
      required: true
  outputs:
    - name: text
      type: string
    - name: title
      type: string
  requirements:
    - Use requests + beautifulsoup
    - Handle timeouts
    - Return partial results on error
EOF
```

### Run Builder

```bash
./services/builder/run.sh
```

### Verification Steps

1. **Tool File Created:**
   ```bash
   test -f tools/website_scraper.py && echo "PASS: Tool file exists" || echo "FAIL: Tool file missing"
   ```

2. **Tool Imports:**
   ```bash
   python -c "from tools.website_scraper import website_scraper; print('PASS: Import works')"
   ```

3. **Dependencies Handled:**
   ```bash
   python -c "
   import requests
   from bs4 import BeautifulSoup
   print('PASS: Dependencies available')
   " || echo "FAIL: Missing dependencies (requests, beautifulsoup4)"
   ```

4. **Tool Runs with Valid URL:**
   ```bash
   python -c "
   from tools.website_scraper import website_scraper
   result = website_scraper(url='https://example.com')
   print(f'Success: {result[\"success\"]}')
   print(f'Result: {result[\"result\"]}')
   print('PASS: Tool runs')
   "
   ```

5. **Error Handling (invalid URL):**
   ```bash
   python -c "
   from tools.website_scraper import website_scraper
   result = website_scraper(url='https://this-domain-does-not-exist-12345.com')
   assert result['success'] == False, 'Should fail for invalid URL'
   assert result['error'] is not None, 'Should have error message'
   print(f'PASS: Error handling works, error={result[\"error\"][:50]}...')
   "
   ```

6. **Contract Compliance:**
   ```bash
   python -c "
   from tools.website_scraper import website_scraper
   result = website_scraper(url='https://example.com')
   assert isinstance(result, dict), 'Result must be dict'
   assert 'result' in result, 'Missing result key'
   assert 'success' in result, 'Missing success key'
   assert 'error' in result, 'Missing error key'
   print('PASS: Contract compliance verified')
   "
   ```

7. **Run Alias Exists:**
   ```bash
   python -c "
   from tools.website_scraper import run
   result = run(url='https://example.com')
   print(f'PASS: run alias works')
   "
   ```

8. **Git Commit Exists:**
   ```bash
   git log --oneline -1 tools/website_scraper.py 2>/dev/null && echo "PASS: Committed" || echo "FAIL: Not committed"
   ```

9. **Redis Registration (if Redis available):**
   ```bash
   redis-cli HGETALL tools:website_scraper 2>/dev/null && echo "PASS: Redis registered" || echo "SKIP: Redis not available"
   ```

### Expected Output

Builder should output **BUILD_COMPLETE** with:
- Tool name: website_scraper
- File path: tools/website_scraper.py
- Test results: PASSED

---

## Running the Tests

### Run Simple Tool Test

```bash
./services/builder/tests/test_simple_tool.sh
```

### Run Complex Tool Test

```bash
./services/builder/tests/test_complex_tool.sh
```

### Run All Tests

```bash
./services/builder/tests/run_all_tests.sh
```

---

## Success Criteria

All tests pass when:

| Test | Criteria |
|------|----------|
| Tool Created | File exists at expected path |
| Imports Work | No ImportError when importing |
| Runs Successfully | Returns dict with success=True for valid input |
| Contract Compliant | Returns dict with result, success, error keys |
| run Alias | `run` function exists and works |
| Git Committed | Tool file appears in git log |
| Redis Registered | Tool metadata in Redis (optional, skip if Redis unavailable) |

---

## Cleanup

After testing, clean up test artifacts:

```bash
# Remove test tools (if not needed)
rm -f tools/hello_world.py tools/website_scraper.py

# Remove test PRD
rm -f services/builder/requests/current_prd.yaml

# Revert git commits (if testing only)
git reset --hard HEAD~2  # Removes last 2 commits (be careful!)
```
