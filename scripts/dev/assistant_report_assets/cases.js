// Filter already-rendered rows; never fetch evidence or recalculate scores.
(() => {
    const rows = Array.from(document.querySelectorAll('#case-index tbody tr'));
    const controls = ['search', 'condition', 'category', 'outcome'].map(
        id => document.getElementById(id)
    );
    const previousButton = document.getElementById('previous');
    const nextButton = document.getElementById('next');
    const pageSize = 25;
    let pageIndex = 0;

    function renderCases() {
        const [search, condition, category, outcome] = controls.map(
            control => control.value.toLowerCase()
        );
        const matchingRows = rows.filter(row =>
            (!search || row.textContent.toLowerCase().includes(search)) &&
            (!condition || row.dataset.condition.toLowerCase() === condition) &&
            (!category || row.dataset.category.toLowerCase() === category) &&
            (!outcome || row.dataset.outcome === outcome)
        );
        const pageCount = Math.max(1, Math.ceil(matchingRows.length / pageSize));
        pageIndex = Math.min(pageIndex, pageCount - 1);

        rows.forEach(row => { row.hidden = true; });
        const firstRow = pageIndex * pageSize;
        matchingRows.slice(firstRow, firstRow + pageSize).forEach(row => {
            row.hidden = false;
        });

        document.getElementById('case-count').textContent =
            `${matchingRows.length} of ${rows.length} cases match`;
        document.getElementById('no-cases').hidden = matchingRows.length !== 0;
        document.getElementById('page-number').textContent =
            `Page ${pageIndex + 1} of ${pageCount}`;
        previousButton.disabled = pageIndex === 0;
        nextButton.disabled = pageIndex + 1 >= pageCount;
    }

    controls.forEach(control => {
        control.addEventListener('input', () => {
            pageIndex = 0;
            renderCases();
        });
    });

    document.getElementById('reset').addEventListener('click', () => {
        controls.forEach(control => { control.value = ''; });
        pageIndex = 0;
        renderCases();
    });
    previousButton.addEventListener('click', () => {
        pageIndex--;
        renderCases();
    });
    nextButton.addEventListener('click', () => {
        pageIndex++;
        renderCases();
    });
    document.querySelector('.pagination').hidden = false;
    renderCases();

    // A deep link must also open enclosing evidence sections.
    function revealLinkedSection() {
        const target = document.getElementById(location.hash.slice(1));
        if (!target) {
            return;
        }
        let ancestor = target;
        while (ancestor) {
            if (ancestor.tagName === 'DETAILS') {
                ancestor.open = true;
            }
            ancestor = ancestor.parentElement;
        }
    }

    window.addEventListener('hashchange', revealLinkedSection);
    revealLinkedSection();
})();
