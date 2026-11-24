# Xorion Presence Audit

Turn observations about a business listing and website into a short action plan. The report shows up to three verified strengths, the first fix to tackle and up to five steps the owner can take. Each fix includes its source, date and a way to check the result.

## Try the fictional example

With Python 3.10 or later, run:

```sh
python3 owner_report.py examples/mill-creek.json report.html
```

Open report.html in a browser. Expand a fix to see the instructions. Use **Print report** to save a PDF. The generator runs locally with the Python standard library. No API key, signup or network request is needed.

## Make your own report

Copy the example, set `sample` to false, and replace the business, town and observations with your own. Supply the observation date and a source URL. Include a fix only after checking that the business owner can take the suggested action. A valid link and a checked box record your review; the generator does not independently verify a claim. Unknown or unsupported findings are omitted.

Use your own observations and materials you have permission to share. Keep customer contact details and private URLs out of externally shared reports. The example is fictional. The generator does not import Google Maps content, customer reviews or prospect lists and does not send email.

See LICENSE and NOTICE.md for distribution terms. Google’s Places policies are available at https://developers.google.com/maps/documentation/places/web-service/policies .
