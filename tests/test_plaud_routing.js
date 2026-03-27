
// Mock n8n environment
const items = [{
    json: {
        subject: "[PLAUD-AutoFlow] Meeting with Client",
        date: "Mon, 14 Feb 2026 12:00:00 GMT",
        snippet: "Here is the summary..."
    },
    binary: {
        attachment_0: {
            fileName: "transcript.txt",
            mimeType: "text/plain",
            data: Buffer.from("Transcript content here").toString('base64')
        },
        attachment_1: {
            fileName: "recording.mp3",
            mimeType: "audio/mpeg",
            data: "..."
        }
    }
}];

// --- Code from 'Route Attachments' Node ---
const email = items[0].json;
const subject = email.subject || 'No Subject';
const dateStr = email.date;
let date = new Date();
if (dateStr) {
    date = new Date(dateStr);
}

// Format: YYYY-MM-DD HH:MM
const yyyy = date.getFullYear();
const mm = String(date.getMonth() + 1).padStart(2, '0');
const dd = String(date.getDate()).padStart(2, '0');
const hh = String(date.getHours()).padStart(2, '0');
const min = String(date.getMinutes()).padStart(2, '0');
const formattedDate = `${yyyy}-${mm}-${dd} ${hh}:${min}`;
const baseFilename = `${formattedDate} ${subject}`.replace(/[\\/:*?"<>|]/g, '');

const attachments = [];
let transcriptText = '';

// Iterate over binary keys (attachment_0, attachment_1, ...)
for (const key in items[0].binary) {
    const file = items[0].binary[key];
    const isTranscript = file.mimeType === 'text/plain' || file.fileName.endsWith('.txt') || file.fileName.endsWith('.md');

    // Route to Transcripts or Plaud Root
    const targetFolderId = isTranscript
        ? '1ZZf0FAoIXR6T_PzlibUEp7fQxiUbrZST' // Transcripts
        : '1lDD6SUh918U6oXjOBB5I9SjFVDAlqjzR'; // Plaud Root

    attachments.push({
        json: {
            fileName: `${baseFilename} - ${file.fileName}`,
            folderId: targetFolderId
        },
        binary: {
            data: file
        }
    });

    // Extract text for Gemini if it's the transcript
    if (isTranscript && !transcriptText) {
        // Basic base64 decode
        transcriptText = Buffer.from(file.data, 'base64').toString('utf-8');
    }
}

const result = [
    attachments,
    [{
        json: {
            transcriptText,
            subject,
            date: formattedDate,
            baseFilename
        }
    }]
];
// ------------------------------------------

console.log("Generated Attachments:", JSON.stringify(result[0].map(a => ({ fileName: a.json.fileName, folderId: a.json.folderId })), null, 2));
console.log("Gemini Input:", JSON.stringify(result[1][0].json, null, 2));
