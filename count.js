const fs = require('fs');
const readline = require('readline');

function countImagesAndHtml(filename) {
  return new Promise((resolve, reject) => {
    const fileStream = fs.createReadStream(filename);
    const rl = readline.createInterface({
      input: fileStream,
      crlfDelay: Infinity
    });

    let imageCount = 0;
    let htmlCount = 0;
    const imageUrls = new Set();
    const htmlUrls = new Set();

    rl.on('line', (line) => {
      const trimmedLine = line.trim().toLowerCase();
      if (line.includes('<image:loc>')) {
        const imageUrl = trimmedLine.match(/<image:loc>(.*?)<\/image:loc>/)?.[1];
        if (imageUrl) {
          imageCount++;
          imageUrls.add(imageUrl);
        }
      } else if (line.includes('<loc>')) {
        const url = trimmedLine.match(/<loc>(.*?)<\/loc>/)?.[1];
        if (url && url.endsWith('.html')) {
          htmlCount++;
          htmlUrls.add(url);
        }
      }
    });

    rl.on('close', () => {
      const imageDuplicates = imageCount - imageUrls.size;
      const htmlDuplicates = htmlCount - htmlUrls.size;
      const totalUrls = imageCount + htmlCount;  // Add this line
      resolve({ imageCount, htmlCount, imageDuplicates, htmlDuplicates, totalUrls });  // Add totalUrls here
    });

    rl.on('error', (err) => {
      reject(err);
    });
  });
}

// Use the function with the .xml file
countImagesAndHtml('data.xml')
  .then(result => {
    console.log(`Total number of image URLs: ${result.imageCount}`);
    console.log(`Number of duplicate image URLs: ${result.imageDuplicates}`);
    console.log(`Total number of .html URLs: ${result.htmlCount}`);
    console.log(`Number of duplicate .html URLs: ${result.htmlDuplicates}`);
    console.log(`Total number of URLs: ${result.totalUrls}`);  // Add this line
  })
  .catch(err => {
    console.error("Error processing the file:", err);
  });
