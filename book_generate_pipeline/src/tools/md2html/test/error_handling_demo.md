# Error Isolation Test - Extreme Chaos

This document contains MANY intentionally broken markdown elements to test error isolation.

## Section 1: Good Content

This section contains normal markdown that should render perfectly despite chaos elsewhere.

- List item 1
- List item 2  
- List item 3

Here's some math that should work: $E = mc^2$

## Section 2: Unpaired Code Fences - BROKEN

This section has unclosed code blocks that should break in monolithic processing:

```python
def broken_function():
    print("This code block is never closed!
    # Missing closing ```

This text should be inside the code block but parser might get confused.

### Subsection 2.1: More Code Chaos

Another broken code block:
```javascript  
function chaos() {
    console.log("Another unclosed block");
    
And some more text that might confuse parsers...

### Subsection 2.2: Mixed Broken Fences

```bash
echo "Starting a command"
# But wait, there's another opening fence!
```python
print("Nested fences - parser nightmare!")
```
# Only one closing fence - which block does it close?

## Section 3: Unpaired Math Delimiters - CHAOS

This section has unmatched math delimiters:

Unmatched dollar signs: $x = 7 and y = 8$ but z = 9$

$$Unclosed display math
\begin{align}  
a &= b \\
c &= d
\end{align}

Missing closing $$

### Subsection 3.1: Inline Code Disasters  

Unclosed inline code: `this code span is never closed
And this text might be treated as code.

More chaos: `another unclosed span and `a closed one` but `another broken

### Subsection 3.2: Mixed Math and Code Chaos

`$math inside broken code span 
$$Display math with unclosed code `inside it
$Inline math with unclosed ``` code fence

## Section 4: Table and List Disasters

This section should render fine despite broken tables elsewhere.

### Subsection 4.1: Broken Tables

| Column A | Column B | 
|----------|
| Missing cell | | Extra pipe |
No closing pipe
| Another | Row | With | Extra | Pipes |

### Subsection 4.2: List Chaos

- List item 1
  - Nested item
    - Deep nested
- Back to level 1
    - Wrong indentation level
  - Another nested
- Final item

## Section 5: Good Content Again

Even with all the chaos above, this section should render normally:

### Subsection 5.1: Normal Math

Proper math: $\sum_{i=1}^n x_i = \frac{a+b}{2}$

Display math:
$$\int_0^1 x^2 dx = \frac{1}{3}$$

### Subsection 5.2: Normal Code

```python
def working_function():
    return "This should work despite chaos above"
    
# Properly closed code block
```

### Subsection 5.3: Normal Table

| Name | Value |
|------|-------|
| X    | 100   |
| Y    | 200   |

## Section 6: Ultimate Chaos - EVERYTHING BROKEN

This section combines ALL possible breakage:

Unclosed code: ```python
print("chaos")
Unclosed math: $x + y
More unclosed math: $$z = 
Broken inline code: `mixed with $math
```javascript  
// Another language fence inside unclosed python
function() {
Broken table:
| Col | 
|--
| Val1 | Val2 | Val3

### Subsection 6.1: Even More Chaos

`$\begin{align}
```bash
$$Nested everything$
`Inline \[display\] $inline$
```

#### Subsubsection 6.1.1: Deep Chaos

This is buried deep in the hierarchy with chaos above.
`Unclosed code at deepest level

#### Subsubsection 6.1.2: More Deep Chaos  

```sql
SELECT * FROM chaos;
-- Never closed

### Subsection 6.2: Final Broken Section

More unpaired elements:
$$$Triple dollar signs
````Four backticks
`````Five backticks  

## Section 7: Recovery Test

If error isolation works, this final section should render perfectly despite ALL the chaos above:

The unit-based system should:
1. Isolate each broken section
2. Show error messages for failed blocks
3. Continue processing other sections normally
4. Not let formatting errors propagate

### Subsection 7.1: Final Verification

- Normal list
- With items
- Should work fine

```python
# Final code block - should work
def test_complete():
    return "Error isolation successful!"
```

Final math: $E = mc^2$ and $$F = ma$$

**End of chaos test. If you can read this normally formatted, error isolation worked!**