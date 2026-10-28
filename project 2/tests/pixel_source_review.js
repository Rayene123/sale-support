async page => {
  const base = new URL(page.url()).origin;
  if (!['127.0.0.1', 'localhost'].includes(new URL(base).hostname)) throw new Error('Use a local preview');
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const citation = {
    record_id: 'review:article-10', chunk_id: 'review:article-10:chunk-0', article: 'Article 10',
    pdf_page: 9, heading_path: ['Livre I'], source_url: 'https://example.invalid/source.pdf',
    text: 'Les livres doivent être conservés dix ans.', quote: 'Ils seront conservés pendant dix ans.',
  };
  const article = {
    ...citation, text: 'Préambule. Ils seront conservés pendant dix ans. Fin.', source_edition: 'Édition 2024',
  };
  const answer = { answer_fr: citation.text + ' [1]', abstain: false, citations: [citation] };
  let currentArticle = article, modelRequests = 0;
  const stream = route => {
    modelRequests++;
    return route.fulfill({contentType: 'application/x-ndjson', body: JSON.stringify({type: 'result', answer}) + '\n'});
  };
  const source = route => route.fulfill({json: currentArticle});
  await page.route('**/ask/stream', stream);
  await page.route('**/articles/review*', source);
  await page.emulateMedia({reducedMotion: 'reduce'});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const cases = [
    ['matching source', {}, true],
    ['whitespace normalization', {text: 'Ils\nseront conservés\tpendant dix ans.'}, true],
    ['missing quote', {text: 'Une version différente et contradictoire.'}, false],
    ['different page', {pdf_page: 99}, false],
    ['different source URL', {source_url: 'https://example.invalid/another.pdf'}, false],
    ['different heading', {heading_path: ['Livre V']}, false],
    ['different article label', {article: 'Article 11'}, false],
  ];
  try {
    for (const [name, changes, matches] of cases) {
      currentArticle = {...article, ...changes};
      await page.goto(base + '/');
      await page.getByRole('textbox', {name: 'Votre question', exact: true}).fill('Question de vérification');
      await page.getByRole('button', {name: 'Consulter les archives >', exact: true}).click();
      await page.getByRole('button', {name: 'Ouvrir les livres', exact: true}).click();
      await page.waitForFunction(() => !document.getElementById('article-status').textContent.includes('Ouverture'));
      const data = await page.evaluate(() => ({
        marked: !!document.querySelector('#book-article mark'),
        status: document.getElementById('article-status').textContent,
        body: document.getElementById('book-article').textContent,
        quote: document.getElementById('book-quote').textContent,
        publisher: document.getElementById('publisher').getAttribute('href'),
      }));
      check(data.marked === matches, name + ': incorrect highlight');
      check(data.quote === citation.quote && data.publisher === citation.source_url, name + ': citation lost');
      if (!matches) {
        check(data.status.includes('non concordantes'), name + ': mismatch warning missing');
        check(!data.body.includes(currentArticle.text), name + ': conflicting article was displayed');
      }
      await page.getByRole('button', {name: 'Refermer', exact: true}).click();
      await page.getByRole('button', {name: 'Nouvelle conversation', exact: true}).click();
    }
    check(modelRequests === cases.length, 'Unexpected retry');
    check(!errors.length, errors.join('\n'));
    return {result: 'PASS', sourceCases: cases.length, originalCitationPreserved: true, browserErrors: errors, paidCalls: 0};
  } finally {
    await page.unroute('**/ask/stream', stream);
    await page.unroute('**/articles/review*', source);
  }
}
