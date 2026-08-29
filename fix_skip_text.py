import re
with open("Manuscript_Draft/draft3.tex", "r", encoding="utf-8") as f:
    text = f.read()

old_sec = r"""\subsection{Skip Rate and Grid Coverage}

    The coverage heatmap (Fig.~\ref{fig:skip_heatmap}) shows the spatial distribution of total touch counts across the grid positions, demonstrating the system's ability to map spatial exploration. By highlighting both unvisited cells (skips) and heavily revisited regions, the metric verifies that the hardware captures complete grid coverage while mapping spatial inconsistencies. Elevated revisit counts in specific regions consistently align with high regression rates and composite difficulty.

    \begin{figure}[!htp]
    \centering
    \includegraphics[width=0.70\columnwidth]{skip_heatmap.pdf}
    \vspace{-4mm}
    \caption{Grid coverage map (aggregated touch counts). Green = 2--5 touches; darker green = 6--7; orange = 8--9 (high revisit rate). The system maps full coverage and highlights heavily re-explored areas.}
    \label{fig:skip_heatmap}
    \vspace{-6mm}
    \end{figure}

    Instances of skipped cells clustered in lower grid rows typically indicate that observation duration, rather than intrinsic word difficulty, drives unvisited regions. Skip rates should therefore be normalized by observation duration when comparing reading behaviors across participants or conditions."""

new_sec = r"""\subsection{Skip Rate and Grid Coverage}

    The coverage heatmap (Fig.~\ref{fig:skip_heatmap}) shows the spatial distribution of total touch counts across the grid positions, demonstrating the system's ability to map spatial exploration. By highlighting baseline touches and heavily revisited regions, the metric verifies that the hardware captures complete grid coverage while mapping spatial inconsistencies. Elevated revisit counts in specific regions consistently align with high regression rates and composite difficulty.

    \begin{figure}[!htp]
    \centering
    \includegraphics[width=0.70\columnwidth]{skip_heatmap.pdf}
    \vspace{-4mm}
    \caption{Grid coverage map (aggregated touch counts). Light green = 1--2 touches; dark green = 3--5 (high revisit rate). The system maps full coverage and successfully highlights heavily re-explored areas without any skipped cells in this session.}
    \label{fig:skip_heatmap}
    \vspace{-6mm}
    \end{figure}

    Because this representative reading session achieved complete spatial coverage (no unvisited cells), it demonstrates the participant's thorough tactile scanning. In sessions where skipped cells cluster in lower grid rows, it typically indicates that observation duration, rather than intrinsic word difficulty, drives unvisited regions. Skip rates should therefore be normalized by observation duration when comparing reading behaviors across participants or conditions."""

text = text.replace(old_sec, new_sec)

with open("Manuscript_Draft/draft3.tex", "w", encoding="utf-8") as f:
    f.write(text)
print("Skip rate section fixed.")
