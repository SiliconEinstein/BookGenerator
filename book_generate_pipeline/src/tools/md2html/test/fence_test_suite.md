# Comprehensive Pipeline Test

## 1. Test Normal Callouts First

> [!NOTE] Single Line Callout
> This is a simple single line callout.

> [!WARNING] Multi-Line Callout
> This is the first line of a multi-line callout.
> 
> This is the second line with some `inline code`.
> And this is the third line.

> [!TIP] Complete Code in Callouts
> You can include complete code blocks in callouts:
> ```python
> def example():
>     return "This should work"
> ```
> And more text after.

## 2. Pre-Code Patching Tests (Robustness - Most Critical)

### 2.1 Dangling Language Fence (Should Be Auto-Patched)

```python
def incomplete_function():
    print("This is missing a closing fence")
    return "auto-patched"

Content after should be captured in code block.

### 2.2 Dangling Plain Fence (Should Be Auto-Patched)

```
This is a python code block with section tag inside.


### 2.3 Incomplete Code in Callout (Should Be Auto-Patched)

> [!BUG] Missing Fence in Callout
> Code block with missing closing fence:
> ```javascript
> function incomplete() {
>     console.log("missing closing fence");
> }
> And this content should be in the code block.

End of callout should be separate.

### 2.4 Complex Dangling Scenario (2n+1 Algorithm Test)
First is a complete bash code block.

```bash
echo "First complete block"

Some text between.

```
Second is an incomplete python cdoe block.

```python
def third_block():
    print("This should be completed too")

Final text content.

## 3. Invalid Standalone Fences (Should Warn After Patching)

### 3.1 Various Invalid Fence Types

```123invalid
Should generate warning - language starts with number.

```-alsoinvalid
Should generate warning - language starts with hyphen.

``` extra text after
Should generate warning - extra content after fence.

```python print("hello")
Should generate warning - code on same line as fence.

```with spaces
Should generate warning - spaces in language name.

### 3.2 Valid Fences (Should Work Normally After Invalid Warnings)

```python
print("This should work fine after warnings")
def valid_function():
    return True
```

```bash
echo "Shell script should work"
ls -la
```

```
Plain fence should work too
with multiple lines
```

## 4. Mixed Complex Scenarios

### 4.1 Invalid Fences Inside Valid Code (Should NOT Warn)

```bash
echo "Testing invalid fences inside code blocks:"
echo "These should be preserved as literal text:"
```123invalid
``` extra text  
```python print("code")
```with spaces in name
echo "All above should be preserved without warnings"
```

### 4.2 Callout with Invalid Fence Inside (Should NOT Warn)

> [!INFO] Documentation Example
> Here's how NOT to write code fences:
> ```123invalid
> This is inside a callout, so no warning should appear.
> ```-invalid too
> These are just examples in documentation.

### 4.3 Mixed Patching and Warning Scenario

```javascript
function incomplete_before_invalid() {
    console.log("This will be auto-patched");

```789invalid
This invalid fence comes after a dangling valid fence.

```json
{
    "valid": "This should work normally",
    "after_warning": true

More content for auto-patching.

## 5. Edge Cases

### 5.1 Consecutive Invalid Fences

```111first
First invalid.

```222second  
Second invalid with trailing space.

```333third
Third invalid.

### 5.2 Invalid Fences with Context

This line has inline `code` before the invalid fence:

```444invalid
Should warn despite inline code before it.

## Final Pipeline Test Complete

All pipeline interactions comprehensively tested!
