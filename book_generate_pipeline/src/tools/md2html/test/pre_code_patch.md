# Comprehensive Dangling Fence Test

## Case 1: Same Language Repeated (Dangling)
```python
# Dangling python (followed by python)
def first():
    pass

Some text in between.

```python
# This python block is properly closed (not dangling)
def second():
    return True
```

## Case 2: Different Languages (Dangling)
```javascript
// Dangling javascript (followed by python)
function broken() {
    console.log("never closed");

```python
# This python block is properly closed (not dangling)
def works():
    return "ok"
```

## Case 3: Language to Plain (Not Dangling)
```bash
# This bash block is properly closed (not dangling)
echo "This bash block is properly closed"
```

## Case 4: Multiple Danglers
```python
# Dangling python (followed by javascript)
def one():
    pass

```javascript
# Dangling javascript (followed by python)
function two() {}

```python
# Dangling python (followed by c++)
def three():
    pass

```c++
# Dangling c++ (followed by python)
int main() {}

```python
# This python block is properly closed (not dangling)
def four():
    return 42
```

## Case 5: Dangling Plain Fences
```
# First plain fence - should pair with second plain fence
some plain code content

## Section After Dangling Plain  
This IS in a code block (between paired plain fences)

```
# A New Section

## Another Section
More normal text.

```
# Third plain fence - DANGLING (breaks python pair below if kept)
even more content

```python
# This python block is properly closed (not dangling)
def proper_function():
    return "This works"
```

## Case 6: Mixed Dangling (Language + Plain)
```javascript
# This javascript block is properly closed (not dangling)
function broken() {}

```
# Plain fence (closes javascript above)
some content

```python
# Dangling python (followed by bash)
def also_broken():
    pass

```bash
# This bash block is properly closed (not dangling)
echo "works fine"
```

## Case 7: End of Document Danglers
```python
# This python block is properly closed (not dangling)
def final():
    print("This is actually properly closed")
```

```
# DANGLING plain fence at EOF (no closing pair)
final content without closing fence

## Final Section
This should be normal text, not in code block.

---
