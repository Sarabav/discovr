## What Discovr Does

Discovr analyzes a business's website, its Google Business Profile, and how it appears across the open web, then scores how visible and understandable that business is to AI systems like ChatGPT, Claude, and Perplexity. It helps small and medium business owners understand why AI systems might not be recommending their business, and gives a prioritized list of what to fix.

Traditional SEO optimizes for search engine result pages, where a human scans a list of blue links and picks one. AI visibility is a different problem: an AI assistant reads across many sources, forms a single answer, and recommends (or fails to recommend) a business directly, often without the user ever visiting a website. A business can rank well in Google and still be invisible to AI assistants if its information is inconsistent, unstructured, unreadable to AI crawlers, or unsupported by any source other than its own marketing.

A business owner submits their website URL, Discovr runs an analysis, and returns a report with an overall score, five category scores, specific findings, and a prioritized list of recommendations with generated fixes. A chatbot answers follow-up questions about the report and about AI visibility generally.

## The Five Scoring Categories

Each category is scored out of 100. The overall score is the average of the categories that could be scored — a category that does not apply to a given business (for example, structured data for a business with no website) is skipped rather than scored zero, so it does not unfairly drag the average down.

A business can have a strong overall score while still having one weak category worth fixing, since problems in a single category can be enough on their own to keep a business out of AI answers.

### NAP Consistency

NAP Consistency checks whether the business name, address, and phone number match across the website and the Google Business Profile listing. AI systems cross-reference multiple sources to confirm a business's identity before recommending it. If the phone number on Google is different from the one on the website, or the business is listed as "Joe's Pizza" in one place and "Joe's Pizza & Pasta LLC" in another, the AI system cannot be fully confident it is looking at the same business, and may hedge, omit the business, or surface outdated details.

Common consistency problems include: a business that moved locations but never updated its Google listing, a business with multiple phone numbers listed across sources without clarifying which is current, and legal business names that differ from the brand name customers actually search for. Trivial formatting differences — "St." versus "Street", or a phone number written with or without parentheses — are not real mismatches and should not be treated as such.

Fixing consistency is usually the fastest win available, since it rarely requires new content, just correcting existing details so they match.

### Structured Data

Structured Data checks whether the website has schema markup, typically using schema.org vocabulary in JSON-LD format, so AI systems can read business details directly as data rather than inferring them from prose. The relevant type for most local businesses is LocalBusiness (or one of its subtypes such as Dentist, Plumber, or Restaurant), with the fields that matter most being name, address, telephone, openingHours, and areaServed.

Without structured data, an AI system has to parse unstructured HTML and guess which text is the business name, which is the address, and which is marketing copy. That guesswork is unreliable and often wrong. With structured data, the same facts are unambiguous and machine-readable. A business with no schema markup at all will score zero here even if its website content is otherwise excellent, because the underlying facts are much harder for an AI system to extract with confidence.

### Content Clarity

Content Clarity checks whether the website's own text clearly and factually describes what the business does, who it serves, where it operates, and which specific services it offers, in language that is easy for both humans and AI systems to summarize. This is different from Structured Data: Content Clarity is about the prose itself, not the markup.

Vague marketing language ("we deliver excellence in every experience") scores poorly because it gives an AI system nothing concrete to repeat back to a user. Specific, factual language ("we are a family dental practice in Riverside offering cleanings, fillings, and pediatric dentistry, open Monday through Saturday") scores well because it directly answers the kinds of questions users ask AI assistants. Service pages that bury the actual service description under long introductory paragraphs, or that never explicitly state the service area, also lower this score.

A useful test: if a stranger reading only the first two sentences of a page cannot say what they would hire this business for and where it operates, the page needs rewriting.

### Crawler Access

Crawler Access checks whether AI systems can physically fetch and read the website's pages at all. This is the most fundamental category, because if a crawler cannot retrieve a page, nothing else on that page matters — the best schema markup and clearest copy in the world are invisible if the page never gets read.

Two things are checked. The first is robots.txt: whether the site explicitly blocks AI crawlers such as GPTBot (OpenAI), ClaudeBot (Anthropic), PerplexityBot, CCBot, or Google-Extended. Many sites block these without the owner ever knowing, because a plugin, template, or hosting default added the rules. It is worth understanding that Google-Extended is not a crawler at all — Google crawls with Googlebot, and Google-Extended is only a switch controlling whether that already-crawled content may be used by Gemini.

The second is unreachable pages: pages that load correctly when a visitor clicks through the site, but return an error when requested directly by URL. This commonly happens with JavaScript-heavy sites whose hosting lacks a catch-all rewrite rule. It matters because AI crawlers always request URLs directly — they do not click through a site the way a person does — so those pages simply do not exist as far as the AI system is concerned.

A related and increasingly important issue is that most independent AI crawlers do not execute JavaScript, unlike Googlebot. A site whose content is injected by JavaScript can therefore be perfectly visible in Google while being nearly blank to ChatGPT, Claude, and Perplexity. This behaviour comes from independent testing rather than official documentation from the AI companies, and it may change over time, so it should be described as the general pattern rather than a guarantee.

### Mentions

Mentions checks whether the business is discussed anywhere on the open web other than its own website and listings — reviews, local forum threads, directory entries, news coverage, community recommendations.

This matters more for AI visibility than it does for traditional SEO. A business asserting on its own site that it is the best plumber in town is a claim with a single, self-interested source. The same claim appearing in an independent forum thread, a review site, and a local directory is corroborated, and AI systems weight corroborated information far more heavily when deciding whether to name a business in an answer. A business with zero independent mentions gives an AI assistant no reason to feel confident recommending it over a competitor that has several.

Note that this category measures whether independent sources exist and what they say — not follower counts or how much the business posts about itself.

## How Recommendations Work

Every analysis produces a list of recommendations, each tied to a specific finding from one of the five categories. Recommendations are ranked by priority (High, Medium, Low) based on expected impact, so the highest-impact fixes appear first. High-priority recommendations typically address findings that actively prevent an AI system from finding, reading, or correctly identifying the business — blocked crawlers, unreachable pages, conflicting contact details, or a complete absence of structured data. Medium-priority recommendations improve clarity or completeness without being blocking issues. Low-priority recommendations are smaller polish items, such as adding optional schema fields.

Each recommendation explains three things: what the issue is, why it matters specifically for AI visibility, and how to fix it, with a concrete first step rather than a vague suggestion.

Some fixes can be generated directly — schema markup blocks, FAQ content, rewritten page copy — using the business's real details, and are presented ready to copy and paste. Others cannot be automated because they require action outside the website, such as correcting a Google Business Profile, changing a hosting configuration, or earning a third-party mention. Those are delivered as precise instructions instead, and Discovr never publishes anything on the business's behalf.

## How to Interpret Your Score

The overall score is the average of the scored categories, and maps to a grade:

80-100 (Strong): the business is generally well understood by AI systems. Focus on the remaining Medium and Low priority recommendations to close small gaps.
60-79 (Needs Improvement): some gaps exist that likely cause AI systems to miss or misrepresent the business in certain cases. Focus on the High priority recommendations first.
Below 60 (Weak): significant gaps exist; AI systems are likely struggling to find or trust information about the business. Start with whichever category has the lowest individual score, since it is usually dragging the overall score down disproportionately.

Because the overall score is an average, two businesses can share the same overall score for very different reasons. Always check the category breakdown, not just the overall number.

One category deserves special attention regardless of the average: if Crawler Access is low, fix that first. Improvements to structured data or content clarity have no effect on pages that AI crawlers cannot retrieve in the first place.

## Examples of Good vs Bad

Good example (NAP Consistency): A bakery lists "Riverside Sweet Bakery, 214 Main St, (555) 010-2222" identically on its website footer and its Google Business Profile. An AI system can confidently confirm the same business across both sources.

Bad example (NAP Consistency): The same bakery lists "Riverside Sweet Bakery" on its website but "Riverside Sweets" on Google, with a phone number that was disconnected two years ago. An AI system may treat these as possibly different businesses, or surface the outdated phone number to a customer.

Good example (Structured Data): A law firm's website includes a LocalBusiness JSON-LD block with the firm's name, address, telephone, opening hours, and service area. AI systems can extract these facts directly and with high confidence.

Bad example (Structured Data): The same law firm's website has no schema markup at all. Its contact details exist only as plain text scattered across several pages, forcing an AI system to guess which text is the current address.

Good example (Content Clarity): A plumbing company's homepage states directly: "We are a licensed plumbing company serving Denver and the surrounding suburbs, specializing in emergency repairs, water heater installation, and drain cleaning." This is short, specific, and easy for an AI system to summarize accurately.

Bad example (Content Clarity): The same plumbing company's homepage instead opens with: "At the heart of everything we do lies a passion for excellence and a commitment to unparalleled service." A reader, human or AI, cannot tell what the business actually does from this text alone.

Good example (Crawler Access): A dental clinic's robots.txt allows all crawlers, and every page — homepage, services, contact — returns correctly when requested directly by URL. Every page is fully readable by every AI system.

Bad example (Crawler Access): A dental clinic's robots.txt contains User-agent: GPTBot followed by Disallow: /, added by a privacy plugin the owner installed and forgot about. ChatGPT cannot read a single page of the site. In a second common variation, the clinic's contact page loads fine when a visitor clicks the menu, but returns a 404 when requested directly, so the page holding the phone number and address is invisible to every AI crawler.

Good example (Mentions): A hair salon appears in a local "best salons" roundup, has reviews on two independent directories, and is recommended by name in a neighbourhood forum thread. Multiple independent sources confirm the salon exists and is well regarded.

Bad example (Mentions): The same salon appears nowhere on the web except its own website and its own social accounts. Every claim about its quality originates from the salon itself, giving an AI system no independent basis for recommending it.

## Tips for Fixing Common AI Visibility Issues
Fixing inconsistent NAP details: pick one canonical version of the business name, address, and phone number, then update the website footer and the Google Business Profile to match exactly, including punctuation and abbreviations.
Adding basic Structured Data quickly: start with a single LocalBusiness JSON-LD block containing name, address, telephone, openingHours, and areaServed. Most website builders and CMS plugins can add this without custom development. Use the business's real details — never placeholder values.
Improving Content Clarity: rewrite the first two sentences of each key page to plainly state what the business does, who it serves, and where, before any marketing language.
Unblocking AI crawlers: open robots.txt and remove any Disallow rules targeting GPTBot, ClaudeBot, PerplexityBot, or CCBot. If a User-agent: * rule blocks everything, narrow it to only the paths that genuinely need protecting.
Fixing unreachable pages: the site needs a catch-all rewrite so any URL serves the app. On Netlify that is a _redirects file containing /* /index.html 200; on Vercel a rewrite in vercel.json; on Apache a .htaccess rule. This is a change for whoever built or hosts the site.
Making a JavaScript-heavy site readable: server-side rendering or pre-rendering key pages ensures the content exists in the HTML itself, rather than only appearing after JavaScript runs. At minimum, make sure the business name, services, location, and contact details are present in the raw HTML.
Earning third-party mentions: answer a real question customers actually ask, publish that answer on the website as a clear page, and share the same answer where the question genuinely comes up — a local forum, a community group, a relevant video. The answer must be genuine and useful; planted promotional posts are removed and can damage a business's reputation.
Prioritizing when everything feels broken: fix Crawler Access first, then High priority items in the lowest-scoring category.

## FAQs

Why is my business not showing up in AI answers? Usually one of five reasons: AI crawlers cannot read your site, your business details are inconsistent across sources, your site has no structured data, your service descriptions are too vague, or nobody independent has ever mentioned you. Check your lowest-scoring category first.

How often should I re-run an analysis? After making changes based on your recommendations, or roughly monthly to catch new inconsistencies as your website and listings change.

Do I need a developer to fix Structured Data issues? Usually not. Adding schema markup often just means pasting a small block of code into your site, which most website builders and CMS plugins support.

Do I need a developer to fix Crawler Access issues? For robots.txt, usually not — it is a plain text file you can edit. For unreachable pages, yes: that is a hosting configuration change and needs whoever built or hosts your site.

What if I don't have a website at all? You can still be scored. NAP Consistency and Mentions are checked from your Google Business Profile and the open web. Structured Data, Content Clarity, and Crawler Access are skipped, since they only exist on a website. Not having a website will be your highest-priority finding, because it leaves AI systems with very little to ground an answer on.

My site looks fine in Google. Why does Discovr say AI systems can't read it? Googlebot runs JavaScript and has years of accumulated data about your site. Most independent AI crawlers fetch the raw HTML and stop there. If your content only appears after JavaScript runs, Google sees a complete page and ChatGPT sees a nearly empty one.

Does Discovr guarantee I will be recommended by AI systems? No. Discovr scores how visible and understandable your business is to AI systems and tells you what to fix, but it does not control how any specific AI system chooses to respond.

Why did my score go down after I redesigned my website? A redesign can remove existing schema markup, replace factual service descriptions with marketing copy, introduce a new phone number format that no longer matches your Google listing, or move the site onto a JavaScript framework whose pages AI crawlers cannot read. Re-run an analysis after any major redesign.

Can a business have a perfect score in one category and still score poorly overall? Yes. Because the overall score is an average, a very strong category cannot fully offset a very weak one.

Does Discovr post to forums or review sites for me? No. Discovr can draft an answer for you to publish yourself, but it never posts anything on your behalf. Authentic mentions are the only ones that help.

What is the difference between NAP Consistency and Structured Data? NAP Consistency is about whether the same facts match across every source. Structured Data is about whether those facts, once correct, are marked up in a machine-readable format on the website. A business can have perfectly consistent details that are still hard for an AI system to extract if none of it is in structured data.

Should I fix Low priority recommendations at all? Eventually, yes, since they still contribute to the overall score — but only after every High and Medium priority recommendation has been addressed.
