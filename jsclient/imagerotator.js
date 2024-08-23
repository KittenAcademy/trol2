class ImageRotator {
   constructor(imageArray, labels, overlays, switchInterval, maxImages, width, height, clickHandler) {
      this.imageArray = imageArray;
      this.labels = labels;
      this.overlays = overlays;
      this.switchInterval = switchInterval;
      this.currentImageIndex = 0;
      this.maxImages = maxImages;

      this.container = document.createElement('div');
      this.container.className = 'image-container';
      // this.container.style.width = `${width}px`;
      // this.container.style.height = `${height}px`;


      this.imgElement = document.createElement('img');
      this.imgElement.src = this.imageArray[0];
      this.container.appendChild(this.imgElement);

      this.labelElements = labels.map((label, index) => {
         const labelElement = document.createElement('div');
         labelElement.className = `label ${['top-left', 'top-right', 'bottom-left', 'bottom-right'][index]}`;
         labelElement.textContent = label;
         this.container.appendChild(labelElement);
         return labelElement;
      });

      this.overlayElements = {};
      this.updateOverlays(overlays);

      this.intervalId = setInterval(() => {
         if(this.imageArray.length == 0) { return }
         this.currentImageIndex = (this.currentImageIndex + 1) % this.imageArray.length;
         this.imgElement.src = this.imageArray[this.currentImageIndex];
      }, this.switchInterval);

      if (clickHandler) {
         this.container.addEventListener('click', clickHandler);
      }
   }

   removeAllImages() {
      this.imageArray.length = 0
   }

   removeImageByIndex(idx) {
      this.ImageArray.splice(idx, 1)
   }

   updateImages(newImageArray) {
      this.imageArray = newImageArray;
      this.currentImageIndex = 0;
      this.imgElement.src = this.imageArray[0];
   }

   addImage(newImage) {
      this.imageArray.push(newImage);
      if (this.imageArray.length > this.maxImages) {
         this.imageArray.shift();
         this.currentImageIndex = this.currentImageIndex - 1;
         if (this.currentImageIndex < 0) {
            this.currentImageIndex = 0;
         }
      }
   }

   updateLabels(newLabels) {
      this.labels = newLabels;
      this.labelElements.forEach((labelElement, index) => {
         labelElement.textContent = this.labels[index];
      });
   }

   updateLabel(index, label) {
      this.labels[index] = label;
      this.labelElements[index].textContent = label;
   }

   addOverlay(name, overlaySrc) {
      if (this.overlayElements[name]) {
         this.container.removeChild(this.overlayElements[name]);
      }
      const overlayElement = document.createElement('img');
      overlayElement.src = overlaySrc;
      overlayElement.className = 'overlay';
      this.container.appendChild(overlayElement);
      this.overlayElements[name] = overlayElement;
   }

   removeOverlay(name) {
      if (this.overlayElements[name]) {
         this.container.removeChild(this.overlayElements[name]);
         delete this.overlayElements[name];
      }
   }

   updateOverlays(newOverlays) {
      Object.keys(this.overlayElements).forEach(name => this.removeOverlay(name));
      Object.entries(newOverlays).forEach(([name, overlaySrc]) => this.addOverlay(name, overlaySrc));
   }

   destroy() {
      clearInterval(this.intervalId);
      this.container.parentNode.removeChild(this.container);
   }
}

