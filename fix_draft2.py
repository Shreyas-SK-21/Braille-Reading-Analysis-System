with open('Manuscript_Draft/draft3.tex', 'r', encoding='utf-8') as f:
    text = f.read()

start_idx = text.find(r'\subsection{Composite Score Sensitivity}')
end_idx = text.find(r'\section{Limitations and Future Work}')

if start_idx != -1 and end_idx != -1:
    new_text = r'''\subsection{Composite Score Sensitivity}

    The composite difficulty score $D$ currently uses fixed heuristic weights ($W_1{=}1.0$, $W_2{=}0.5$, $W_3{=}2.0$, $W_4{=}1.5$). To demonstrate adaptability for different pedagogical needs, we compared word difficulty rankings across varying weight configurations. The core high-difficulty cluster (\textit{Ant}, \textit{Socks}, \textit{Frog}) dominates across all presets, but their relative rankings shift logically: a Speed-Focused preset ($W_3{=}3.0$) elevates slow-read words, shifting \textit{Socks} to the \#1 rank and pushing \textit{Cow} ahead of \textit{Frog}; conversely, an Accuracy-Focused preset ($W_1{=}2.0$) strongly penalizes high-regression words, elevating \textit{Frog} and \textit{Alligator} to the \#1 and \#2 most difficult words overall.

    '''
    text = text[:start_idx] + new_text + text[end_idx:]
    with open('Manuscript_Draft/draft3.tex', 'w', encoding='utf-8') as f:
        f.write(text)
    print('Replaced section successfully.')
else:
    print('Could not find boundaries.')
