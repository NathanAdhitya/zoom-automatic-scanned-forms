const regex = /^.{8} From  (.+)  to  Everyone:$/gm;

function parse() {
    const contents = document.getElementById("contents").value;
    // regex the way
    const results = contents.matchAll(regex);

    const participants = new Set();

    // loop over
    var done = false;
    while (!done) {
        const res = results.next();
        console.log(res);
        done = res.done;
        if (done) continue;

        // parse the value
        participants.add(res.value[1]);
    }

    // modify the participants table
    const tbl = document.getElementById("participants");
    // empty table
    tbl.innerHTML = "";
    document.getElementById("count").innerText = `Participants (${participants.size})`;
    Array.from(participants).sort().forEach((value, index) => {
        var row = tbl.appendChild(document.createElement("tr"));
        row.appendChild(document.createElement("td"))
            .appendChild(document.createTextNode(index + 1))
        row.appendChild(document.createElement("td"))
            .appendChild(document.createTextNode(value))
    });
}