import re

with open('Manuscript_Draft/draft3.tex', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Representative dataset
old_pilot = ('The results presented in this section were obtained through a\n'
             '    pilot evaluation conducted with sighted participants interacting\n'
             '    with the $7\\times7$ grid surface. Ethical approval was taken from the Institution Review Board (IRB) for sighted and healthy subjects to evaluate the prototype. This evaluation was performed\n'
             '    to validate system functionality, metric computation, and\n'
             '    visualization pipeline.')
new_pilot = ('The results presented in this section were obtained through a\n'
             '    pilot evaluation with sighted participants interacting\n'
             '    with the $7\\times7$ grid surface (approved by the Institutional Review Board). '
             'To effectively demonstrate the system\'s capabilities, the figures present a '
             'representative aggregated reading dataset; formal variance tracking and '
             'multi-session statistical analysis are deferred to the upcoming clinical trials. '
             'This evaluation validates system functionality, metric computation, and the visualization pipeline.')
text = text.replace(old_pilot, new_pilot)
print('Fix 1 (Representative dataset):', 'representative aggregated reading dataset' in text)

# 2. BOM
old_bom = 'Even with all passive components, cabling, and a perfboard, the complete hardware bill of materials is bounded at approximately \\$14--18\\,USD per unit.'
new_bom = 'The remainder of the \\$14--18\\,USD hardware bill of materials is accounted for by ubiquitous laboratory supplies: a prototyping breadboard, $1\\,\\mathrm{M}\\Omega$ resistors, and jumper wiring.'
text = text.replace(old_bom, new_bom)
print('Fix 2 (BOM):', 'prototyping breadboard' in text)

# 3. Fig 6
old_fig6 = 'spatially localised hesitation targets.}'
new_fig6 = 'spatially localised hesitation targets. Words omitted from the chart recorded exactly zero regressions.}'
text = text.replace(old_fig6, new_fig6)
print('Fix 3 (Fig 6 missing words):', 'exactly zero regressions' in text)

# 4. Fig 8
old_fig8 = 'Red ($D\\geq0.90$) = high effort; yellow ($0.50\\leq D<0.90$) = moderate; white = low.'
new_fig8 = 'The continuous gradient maps directly to effort: dark red denotes high difficulty, while light yellow/white denotes low difficulty.'
text = text.replace(old_fig8, new_fig8)
print('Fix 4 (Fig 8 colormap):', 'continuous gradient maps' in text)

with open('Manuscript_Draft/draft3.tex', 'w', encoding='utf-8') as f:
    f.write(text)
print('Done!')
