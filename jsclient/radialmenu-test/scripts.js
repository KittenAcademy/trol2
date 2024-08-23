function showOptions(event) {
    const optionsContainer = document.getElementById('optionsContainer');
    const rect = event.target.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const offset = -90;  // By default item 1 is directly to the right, this will offset it.

    optionsContainer.style.left = `${x}px`;
    optionsContainer.style.top = `${y}px`;

    const radius = 250; // Radius for the radial arrangement
    const options = document.querySelectorAll('.option');
    const angleStep = 360 / options.length;

    options.forEach((option, index) => {
        const angle = (angleStep * index) + offset;
        const optionX = radius * Math.cos(angle * (Math.PI / 180)) - option.offsetWidth / 2;
        const optionY = radius * Math.sin(angle * (Math.PI / 180)) - option.offsetHeight / 2;

        option.style.left = `${optionX}px`;
        option.style.top = `${optionY}px`;
    });

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

