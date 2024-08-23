function showOptions(event) {
    const optionsContainer = document.getElementById('optionsContainer');
    const rect = event.target.getBoundingClientRect();
    const x = rect.left + window.scrollX + rect.width / 2;
    const y = rect.top + window.scrollY + rect.height / 2;

    optionsContainer.style.top = `${y}px`;
    optionsContainer.style.left = `${x}px`;
    optionsContainer.classList.toggle('hidden');
    setTimeout(() => {
        optionsContainer.style.opacity = optionsContainer.style.opacity == '1' ? '0' : '1';
    }, 0);
}

function optionSelected(option, divId) {
    console.log(`Option selected: ${option} from div: ${divId}`);
    // Your custom function can be called here
    // customFunction(option, divId);

    // Hide options after selection
    const optionsContainer = document.getElementById('optionsContainer');
    optionsContainer.style.opacity = '0';
    setTimeout(() => {
        optionsContainer.classList.add('hidden');
    }, 300);
}

