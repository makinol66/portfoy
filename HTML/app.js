const defaultFavorites = ["AFYON", "AKMGY", "AYDEM", "AYES", "BLUME", "CRDFA", "FZLGY", "GUBRF", "ISYAT", "LMKDC", "MIATK", "REEDR", "THYAO", "USDTR", "YATAS"];

document.addEventListener('DOMContentLoaded', () => {
    const favoritesList = document.getElementById('favoritesList');
    const newStockInput = document.getElementById('newStockInput');
    const addStockBtn = document.getElementById('addStockBtn');
    
    const stockTitle = document.getElementById('stockTitle');
    const taContainer = document.getElementById('tv_ta_container');
    const customIntervalsDiv = document.getElementById('custom-intervals');
    const intervalButtons = document.querySelectorAll('.interval-btn');

    let currentSymbol = "";
    let currentInterval = "1D";

    let savedFavorites = JSON.parse(localStorage.getItem('webFavoriler'));
    if (!savedFavorites || savedFavorites.length === 0) {
        savedFavorites = defaultFavorites;
        localStorage.setItem('webFavoriler', JSON.stringify(savedFavorites));
    }

    intervalButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            intervalButtons.forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            
            currentInterval = e.target.getAttribute('data-val');
            if (currentSymbol) {
                loadAnalysis(currentSymbol, currentInterval);
            }
        });
    });

    function renderFavorites() {
        favoritesList.innerHTML = ''; 
        savedFavorites.forEach(stock => {
            const li = document.createElement('li');
            li.textContent = stock;
            
            li.addEventListener('click', () => {
                currentSymbol = stock;
                customIntervalsDiv.style.display = "flex"; 
                
                document.querySelectorAll('#favoritesList li').forEach(el => el.style.borderColor = 'transparent');
                li.style.borderColor = '#29b6f6';

                loadAnalysis(currentSymbol, currentInterval); 
            });

            const deleteBtn = document.createElement('span');
            deleteBtn.textContent = '❌';
            deleteBtn.className = 'delete-btn';
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation(); 
                removeStock(stock);
            });

            li.appendChild(deleteBtn);
            favoritesList.appendChild(li);
        });
    }

    addStockBtn.addEventListener('click', () => {
        const newStock = newStockInput.value.trim().toUpperCase();
        if (newStock && !savedFavorites.includes(newStock)) {
            savedFavorites.push(newStock);
            savedFavorites.sort(); 
            localStorage.setItem('webFavoriler', JSON.stringify(savedFavorites));
            newStockInput.value = '';
            renderFavorites();
        }
    });

    function removeStock(stockToRemove) {
        savedFavorites = savedFavorites.filter(stock => stock !== stockToRemove);
        localStorage.setItem('webFavoriler', JSON.stringify(savedFavorites));
        renderFavorites();
        
        if(currentSymbol === stockToRemove) {
            stockTitle.textContent = "Hisse Seçiniz";
            taContainer.innerHTML = '<p style="text-align: center; color: #888; margin-top: 50px;">Teknik analizini görmek istediğiniz hisseye listeden tıklayın.</p>';
            customIntervalsDiv.style.display = "none";
            currentSymbol = "";
        }
    }

    function loadAnalysis(symbol, interval) {
        stockTitle.textContent = symbol + " - Teknik Analiz";
        const tvSymbol = symbol === "USDTR" ? symbol : `BIST:${symbol}`; 

        taContainer.innerHTML = ''; 
        
        const script = document.createElement('script');
        script.src = "https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js";
        script.async = true;
        script.innerHTML = JSON.stringify({
            "interval": interval, 
            "width": "100%",
            "isTransparent": true,
            "height": "100%", // CSS'te belirlediğimiz 550px'i tam olarak dolduracak
            "symbol": tvSymbol,
            "showIntervalTabs": false, 
            "displayMode": "multiple",
            "locale": "tr",
            "colorTheme": "dark"
        });
        taContainer.appendChild(script);
    }

    renderFavorites();
});