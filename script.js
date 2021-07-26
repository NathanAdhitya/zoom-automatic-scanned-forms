const { degrees, PDFDocument, rgb, StandardFonts } = PDFLib

function _base64ToArrayBuffer(base64) {
    var binary_string = window.atob(base64);
    var len = binary_string.length;
    var bytes = new Uint8Array(len);
    for (var i = 0; i < len; i++) {
        bytes[i] = binary_string.charCodeAt(i);
    }
    return bytes.buffer;
}

$("#download").click(
    async function () {
        $("#download").attr("disabled", "true").text("Processing");
        $('#qr_code img').removeAttr('src');
        $("#download-backup").removeAttr("href").removeAttr("style")
        const val = String.prototype.trim.call(document.getElementById("code").value);
        if (val === "") {
            $("#download").removeAttr("disabled").text("Download Final PDF");
            alert("Kode harus diisi!");
            return;
        }
        var qrcode = new QRious();
        qrcode.set({
            value: document.getElementById("code").value,
            size: 300,
            level: "M",
        });

        const pngImageBytes = await fetch(qrcode.toDataURL()).then(res => res.arrayBuffer())

        // get the input
        /*const fileInput = document.getElementById("master");
        const file = fileInput.files[0];*/

        // Load a PDFDocument from the existing PDF bytes (arrayBuffer)
        // const pdfDoc = await PDFDocument.load(await file.arrayBuffer())
        try {
            const pdfDoc = await PDFDocument.load(await fetch("master-r1.pdf").then(res => res.arrayBuffer()));

            // embed the image
            const pngImage = await pdfDoc.embedPng(pngImageBytes);

            // Get the first page of the document
            const pages = pdfDoc.getPages()
            const firstPage = pages[0]

            const pngDims = pngImage.scale(0.3)

            // Get the width and height of the first page
            const { width, height } = firstPage.getSize()

            // Draw a string of text diagonally across the first page
            firstPage.drawImage(pngImage, {
                x: width - pngDims.width * 10 / 9,
                y: height - pngDims.height * 10 / 9,
                width: pngDims.width,
                height: pngDims.height
            })

            // Serialize the PDFDocument to bytes (a Uint8Array)
            const pdfBytes = await pdfDoc.save()

            // Trigger the browser to download the PDF document
            download(pdfBytes, "Formulir.pdf", "application/pdf");

            // turn the button back
            $("#download").removeAttr("disabled").text("Download Final PDF");
            setTimeout(function () {
                const blob = new Blob([pdfBytes], { type: "application/pdf" });
                const url = window.URL.createObjectURL(blob);
                $("#download-backup").attr("style", "display: block").attr("href", url)
            }, 1000);
        } catch (e) {
            $("#download").text("Error, try another browser.")
        }

    }
);
