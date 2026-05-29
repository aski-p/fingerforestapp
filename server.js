import cron from 'node-cron';
import express from 'express';
import { XMLParser } from 'fast-xml-parser';
import * as cheerio from 'cheerio';
import { createClient } from '@supabase/supabase-js';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.PORT || 4173);
const supabaseUrl = process.env.VITE_SUPABASE_URL || process.env.SUPABASE_URL;
const supabasePublishableKey = process.env.VITE_SUPABASE_PUBLISHABLE_KEY || process.env.SUPABASE_PUBLISHABLE_KEY;
const supabaseServiceKey = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY;
const crawlSecret = process.env.CRAWL_SECRET;
const requestTimeoutMs = Number(process.env.CRAWL_REQUEST_TIMEOUT_MS || 12000);
const maxItemsPerSource = Number(process.env.CRAWL_MAX_ITEMS_PER_SOURCE || 50);
const newsListLimit = Number(process.env.NEWS_LIST_LIMIT || 5000);
const minCachedArticleContentLength = Number(process.env.CRAWL_MIN_ARTICLE_CONTENT_LENGTH || 700);
const newsDetailBackfillLimit = Number(process.env.NEWS_DETAIL_BACKFILL_LIMIT || 300);
const clinicalTrialBackfillYears = Number(process.env.CLINICAL_TRIAL_BACKFILL_YEARS || 20);
const clinicalTrialBackfillPageSize = Number(process.env.CLINICAL_TRIAL_BACKFILL_PAGE_SIZE || 100);
const clinicalTrialBackfillMaxPages = Number(process.env.CLINICAL_TRIAL_BACKFILL_MAX_PAGES || 8);
const clinicalTrialBackfillMaxRows = Number(process.env.CLINICAL_TRIAL_BACKFILL_MAX_ROWS || 300);
const readerFallbackBaseUrl = process.env.READER_FALLBACK_BASE_URL || 'https://r.jina.ai/http://';
const dataDir = path.join(__dirname, 'data');
const newsStorePath = path.join(dataDir, 'news_articles.json');
const scheduleStorePath = path.join(dataDir, 'schedule_entries.json');

const app = express();
app.use(express.json({ limit: '8mb' }));

const adminSupabase =
  supabaseUrl && supabaseServiceKey
    ? createClient(supabaseUrl, supabaseServiceKey, {
        auth: { persistSession: false },
      })
    : null;

const sources = [
  {
    id: 'nord-news',
    name: 'National Organization for Rare Disorders (NORD)',
    type: 'rss',
    url: 'https://rarediseases.org/feed/',
    baseUrl: 'https://rarediseases.org',
    alwaysRelevant: true,
  },
  {
    id: 'eurordis-news',
    name: 'EURORDIS - Rare Diseases Europe',
    type: 'rss',
    url: 'https://www.eurordis.org/feed/',
    baseUrl: 'https://www.eurordis.org',
    alwaysRelevant: true,
  },
  {
    id: 'global-genes',
    name: 'Global Genes',
    type: 'html',
    url: 'https://globalgenes.org/news/',
    baseUrl: 'https://globalgenes.org',
    itemSelector: 'a[href*="/story/"], a[href*="/news/"], article a[href]',
    alwaysRelevant: true,
  },
  {
    id: 'rare-disease-advisor',
    name: 'Rare Disease Advisor',
    type: 'html',
    url: 'https://www.rarediseaseadvisor.com/news/',
    baseUrl: 'https://www.rarediseaseadvisor.com',
    itemSelector: 'a[href*="/news/"], article a[href]',
    alwaysRelevant: true,
  },
  {
    id: 'rare-x',
    name: 'RARE-X',
    type: 'rss',
    url: 'https://rare-x.org/feed/',
    baseUrl: 'https://rare-x.org',
    alwaysRelevant: true,
  },
  {
    id: 'rare-diseases-international',
    name: 'Rare Diseases International',
    type: 'rss',
    url: 'https://www.rarediseasesinternational.org/feed/',
    baseUrl: 'https://www.rarediseasesinternational.org',
    alwaysRelevant: true,
  },
  {
    id: 'rare-disease-day',
    name: 'Rare Disease Day',
    type: 'rss',
    url: 'https://www.rarediseaseday.org/feed/',
    baseUrl: 'https://www.rarediseaseday.org',
    alwaysRelevant: true,
  },
  {
    id: 'everylife-foundation',
    name: 'EveryLife Foundation for Rare Diseases',
    type: 'rss',
    url: 'https://everylifefoundation.org/feed/',
    baseUrl: 'https://everylifefoundation.org',
    alwaysRelevant: true,
  },
  {
    id: 'patient-worthy',
    name: 'Patient Worthy',
    type: 'rss',
    url: 'https://patientworthy.com/feed/',
    baseUrl: 'https://patientworthy.com',
    alwaysRelevant: true,
  },
  {
    id: 'irdirc',
    name: 'International Rare Diseases Research Consortium (IRDiRC)',
    type: 'rss',
    url: 'https://irdirc.org/feed/',
    baseUrl: 'https://irdirc.org',
    alwaysRelevant: true,
  },
  {
    id: 'rare-revolution',
    name: 'Rare Revolution Magazine',
    type: 'rss',
    url: 'https://rarerevolutionmagazine.com/feed/',
    baseUrl: 'https://rarerevolutionmagazine.com',
    alwaysRelevant: true,
  },
  {
    id: 'rare-voices-australia',
    name: 'Rare Voices Australia',
    type: 'rss',
    url: 'https://www.rarevoices.org.au/feed/',
    baseUrl: 'https://www.rarevoices.org.au',
    alwaysRelevant: true,
  },
  {
    id: 'cord-canada',
    name: 'Canadian Organization for Rare Disorders',
    type: 'html',
    url: 'https://www.raredisorders.ca/news',
    baseUrl: 'https://www.raredisorders.ca',
    itemSelector: 'a[href*="/news/story/"]',
    alwaysRelevant: true,
  },
  {
    id: 'genetic-alliance-uk',
    name: 'Genetic Alliance UK',
    type: 'rss',
    url: 'https://geneticalliance.org.uk/feed/',
    baseUrl: 'https://geneticalliance.org.uk',
    alwaysRelevant: true,
  },
  {
    id: 'beacon-uk',
    name: 'Beacon for Rare Diseases',
    type: 'rss',
    url: 'https://www.rarebeacon.org/feed/',
    baseUrl: 'https://www.rarebeacon.org',
    alwaysRelevant: true,
  },
  {
    id: 'unique-rare-chromosome',
    name: 'Unique - Rare Chromosome Disorder Support Group',
    type: 'rss',
    url: 'https://www.rarechromo.org/feed/',
    baseUrl: 'https://www.rarechromo.org',
    alwaysRelevant: true,
  },
  {
    id: 'rare-disorders-nz',
    name: 'Rare Disorders New Zealand',
    type: 'html',
    url: 'https://raredisorders.org.nz/learn/category/news/',
    baseUrl: 'https://raredisorders.org.nz',
    itemSelector: 'article a[href], h2 a[href], h3 a[href], .card a[href]',
    alwaysRelevant: true,
  },
  {
    id: 'rare-diseases-south-africa',
    name: 'Rare Diseases South Africa',
    type: 'html',
    url: 'https://www.rarediseases.co.za/blog',
    baseUrl: 'https://www.rarediseases.co.za',
    itemSelector: 'article a[href], h2 a[href], h3 a[href], a[href*="/post/"]',
    alwaysRelevant: true,
  },
  {
    id: 'raddar-japan',
    name: 'Rare Disease Data Registry of Japan',
    type: 'rss',
    url: 'https://www.raddarj.org/feed/',
    baseUrl: 'https://www.raddarj.org',
    alwaysRelevant: true,
  },
  {
    id: 'shionogi-news',
    name: 'Shionogi News',
    type: 'html',
    url: 'https://www.shionogi.com/us/en/news.html',
    baseUrl: 'https://www.shionogi.com',
    itemSelector: 'a[href*="/news/"]',
    alwaysRelevant: true,
  },
  {
    id: 'shionogi-clinical-trials',
    name: 'Shionogi Clinical Trials',
    type: 'seed',
    baseUrl: 'https://www.shionogi.com',
    alwaysRelevant: true,
    news_category: 'clinical_trial',
    items: [
      {
        url: 'https://clinicaltrials.gov/study/NCT06717438',
        title_original:
          "Phase 2 study of zatolmilast in PPP2R5D neurodevelopmental disorder (Jordan's syndrome)",
        summary_original:
          "Shionogi lists a Phase 2 randomized, double-blind, placebo-controlled clinical trial assessing safety and tolerability of zatolmilast in participants ages 9-45 years with PPP2R5D neurodevelopmental disorder, also called Jordan's syndrome.",
        published_at: '2025-09-16T00:00:00.000Z',
      },
      {
        url: 'https://www.clinicaltrials.gov/study/NCT05367960?intr=zatolmilast&rank=1',
        title_original: 'Open-label extension study of zatolmilast in Fragile X syndrome',
        summary_original:
          'Shionogi lists an open-label extension study evaluating safety and cognitive assessments for participants with Fragile X syndrome after completing EXPERIENCE-204 or EXPERIENCE-301.',
        published_at: '2025-09-16T00:00:00.000Z',
      },
      {
        url: 'https://clinicaltrials.gov/study/NCT07123155',
        title_original: 'Phase 2 study of S-606001 as add-on therapy in late-onset Pompe disease',
        summary_original:
          'Shionogi lists a Phase 2 multicenter, randomized, placebo-controlled, double-blind study of S-606001 as an add-on to enzyme replacement therapy in patients with late-onset Pompe disease.',
        published_at: '2025-09-16T00:00:00.000Z',
      },
      {
        url: 'https://www.shionogi.com/us/en/innovation/clinical-trials.html',
        title_original: 'Shionogi Clinical Trials in the U.S.',
        summary_original:
          'Shionogi maintains a clinical trials page for studies that include rare disease programs, with links to trial identifiers and study descriptions.',
        published_at: '2025-09-16T00:00:00.000Z',
      },
    ],
  },
  {
    id: 'clinicaltrials-gov-rare-disease',
    name: 'ClinicalTrials.gov - Rare Disease Trials',
    type: 'clinicaltrials',
    url: 'https://clinicaltrials.gov/api/v2/studies',
    baseUrl: 'https://clinicaltrials.gov',
    query: {
      'query.cond': 'Rare Diseases',
      'filter.advanced': 'AREA[StudyType]Interventional',
      sort: 'LastUpdatePostDate:desc',
    },
    alwaysRelevant: true,
    news_category: 'clinical_trial',
  },
  {
    id: 'clinicaltrials-gov-orphan-drug',
    name: 'ClinicalTrials.gov - Orphan Drug Trials',
    type: 'clinicaltrials',
    url: 'https://clinicaltrials.gov/api/v2/studies',
    baseUrl: 'https://clinicaltrials.gov',
    query: {
      'query.term': 'orphan drug rare disease',
      'filter.advanced': 'AREA[StudyType]Interventional',
      sort: 'LastUpdatePostDate:desc',
    },
    alwaysRelevant: true,
    news_category: 'clinical_trial',
  },
  {
    id: 'google-news-rare-clinical-trials',
    name: 'Google News - Rare Disease Clinical Trials',
    type: 'rss',
    url: 'https://news.google.com/rss/search?q=%22rare%20disease%22%20%28%22clinical%20trial%22%20OR%20%22Phase%202%22%20OR%20%22Phase%203%22%20OR%20%22orphan%20drug%22%20OR%20%22gene%20therapy%22%29&hl=en-US&gl=US&ceid=US:en',
    baseUrl: 'https://news.google.com',
    alwaysRelevant: true,
    news_category: 'clinical_trial',
  },
  {
    id: 'google-news-ppp2r5d',
    name: 'Google News - PPP2R5D',
    type: 'rss',
    url: 'https://news.google.com/rss/search?q=PPP2R5D%20OR%20%22Jordan%20syndrome%22%20OR%20%22PPP2%20syndrome%20type%20R5D%22&hl=en-US&gl=US&ceid=US:en',
    baseUrl: 'https://news.google.com',
    alwaysRelevant: true,
  },
  {
    id: 'known-ppp2r5d-trials',
    name: 'PPP2R5D 임상시험 주요 기사',
    type: 'seed',
    baseUrl: 'https://www.shionogi.com',
    alwaysRelevant: true,
    items: [
      {
        url: 'https://www.shionogi.com/us/en/news/2025/02/shionogi-and-jordans-guardian-angels-announce-first-ever-human-drug-study-for-jordans-syndrome-an-ultra-rare-genetic-neurodevelopmental-disorder.html',
        title_original:
          "Shionogi and Jordan's Guardian Angels Announce First-Ever Human Drug Study for Jordan's Syndrome, an Ultra-Rare Genetic Neurodevelopmental Disorder",
        summary_original:
          'Shionogi and Jordan’s Guardian Angels announced a Phase 2 clinical trial evaluating zatolmilast in people with PPP2 syndrome type R5D, commonly referred to as Jordan’s Syndrome.',
        published_at: '2025-02-04T00:00:00.000Z',
      },
      {
        url: 'https://www.biospace.com/press-releases/shionogi-and-jordans-guardian-angels-announce-first-ever-human-drug-study-for-jordans-syndrome-an-ultra-rare-genetic-neurodevelopmental-disorder',
        title_original:
          "Shionogi and Jordan's Guardian Angels Announce First-Ever Human Drug Study for Jordan's Syndrome, an Ultra-Rare Genetic Neurodevelopmental Disorder",
        summary_original:
          'The Phase 2 randomized, double-blind, placebo-controlled study will evaluate zatolmilast in Jordan’s Syndrome.',
        published_at: '2025-02-04T00:00:00.000Z',
      },
    ],
  },
  {
    id: 'feder-spain',
    name: 'FEDER - Federación Española de Enfermedades Raras',
    type: 'html',
    url: 'https://www.enfermedades-raras.org/actualidad/noticias',
    baseUrl: 'https://www.enfermedades-raras.org',
    itemSelector: 'article a[href], .item-title a[href], .page-header a[href], a[href*="/actualidad/noticias/"]',
    alwaysRelevant: true,
  },
  {
    id: 'alliance-maladies-rares-france',
    name: 'Alliance Maladies Rares',
    type: 'rss',
    url: 'https://alliance-maladies-rares.org/feed/',
    baseUrl: 'https://alliance-maladies-rares.org',
    alwaysRelevant: true,
  },
  {
    id: 'uniamo-italy',
    name: 'UNIAMO Federazione Italiana Malattie Rare',
    type: 'rss',
    url: 'https://www.uniamo.org/feed/',
    baseUrl: 'https://www.uniamo.org',
    alwaysRelevant: true,
  },
  {
    id: 'raredis-bulgaria',
    name: 'Institute for Rare Diseases Bulgaria',
    type: 'rss',
    url: 'https://www.raredis.org/en/feed/',
    baseUrl: 'https://www.raredis.org',
    alwaysRelevant: true,
  },
  {
    id: 'ncats-news',
    name: 'NCATS News',
    type: 'html',
    url: 'https://ncats.nih.gov/news-events/news',
    baseUrl: 'https://ncats.nih.gov',
    itemSelector: 'a[href*="/news-events/news/"]',
  },
  {
    id: 'nih-reporter-rare-diseases',
    name: 'NIH Research Matters',
    type: 'html',
    url: 'https://www.nih.gov/news-events/nih-research-matters',
    baseUrl: 'https://www.nih.gov',
    itemSelector: 'a[href*="/news-events/nih-research-matters/"]',
  },
  {
    id: 'fda-rare-diseases',
    name: 'FDA Newsroom',
    type: 'html',
    url: 'https://www.fda.gov/news-events/fda-newsroom/press-announcements',
    baseUrl: 'https://www.fda.gov',
    itemSelector: 'a[href*="/news-events/press-announcements/"]',
  },
  {
    id: 'fda-orphan-products',
    name: 'FDA Orphan Products',
    type: 'html',
    url: 'https://www.fda.gov/industry/developing-products-rare-diseases-conditions',
    baseUrl: 'https://www.fda.gov',
    itemSelector: 'a[href]',
  },
  {
    id: 'ema-whats-new',
    name: 'European Medicines Agency (EMA)',
    type: 'html',
    url: 'https://www.ema.europa.eu/en/news-events/whats-new',
    baseUrl: 'https://www.ema.europa.eu',
    itemSelector: 'a[href*="/en/news"], a[href*="/en/medicines"]',
  },
  {
    id: 'ema-rss-news',
    name: 'European Medicines Agency - News',
    type: 'rss',
    url: 'https://www.ema.europa.eu/en/rss/news.xml',
    baseUrl: 'https://www.ema.europa.eu',
  },
  {
    id: 'orphanet-news',
    name: 'Orphanet',
    type: 'html',
    url: 'https://www.orpha.net/en/news',
    baseUrl: 'https://www.orpha.net',
    itemSelector: 'a[href]',
    alwaysRelevant: true,
  },
  {
    id: 'orphanet-journal',
    name: 'Orphanet Journal of Rare Diseases',
    type: 'html',
    url: 'https://ojrd.biomedcentral.com/articles',
    baseUrl: 'https://ojrd.biomedcentral.com',
    itemSelector: 'a[href*="/articles/10.1186/"]',
    alwaysRelevant: true,
  },
  {
    id: 'ern-rnd',
    name: 'European Reference Network on Rare Neurological Diseases',
    type: 'html',
    url: 'https://www.ern-rnd.eu/news/',
    baseUrl: 'https://www.ern-rnd.eu',
    itemSelector: 'article a[href], .post a[href], a[href*="/news/"]',
    alwaysRelevant: true,
  },
  {
    id: 'snuh-rare-disease-center',
    name: '서울대학교병원 희귀질환센터',
    type: 'wordpress',
    url: 'https://raredisease.snuh.org/wp-json/wp/v2/posts',
    baseUrl: 'https://raredisease.snuh.org',
    maxItems: 900,
    perPage: 100,
    alwaysRelevant: true,
  },
  {
    id: 'snuh-child-lectures',
    name: '서울대학교어린이병원 강좌안내',
    type: 'html',
    url: 'https://child.snuh.org/main.do',
    baseUrl: 'https://child.snuh.org',
    itemSelector: 'a[href*="/about/news/lecture/view.do"]',
    alwaysRelevant: true,
  },
  {
    id: 'snuh-child-news',
    name: '서울대학교어린이병원 병원소식',
    type: 'html',
    url: 'https://child.snuh.org/main.do',
    baseUrl: 'https://child.snuh.org',
    itemSelector: 'a[href*="/board/B051/view.do"]',
  },
  {
    id: 'kdca-search',
    name: '질병관리청',
    type: 'html',
    url: 'https://www.kdca.go.kr/search/search.es?mid=a20101000000&act=view&searchField=ALL&searchKeyword=%ED%9D%AC%EA%B7%80%EC%A7%88%ED%99%98',
    baseUrl: 'https://www.kdca.go.kr',
    itemSelector: 'a[href]',
  },
  {
    id: 'known-korea-rare-disease',
    name: '국내 희귀질환 주요 기사',
    type: 'seed',
    baseUrl: 'https://raredisease.snuh.org',
    alwaysRelevant: true,
    items: [
      {
        url: 'https://raredisease.snuh.org/about-us/notice/opening-ceremony-symposium/',
        title_original: '서울대학교병원 희귀질환센터 개소식 및 심포지엄 개최',
        summary_original:
          '서울대학교병원은 어린이병원 임상 강의실에서 희귀질환센터 개소식 및 심포지엄을 개최하고 희귀질환 연구와 센터 역할을 논의했습니다.',
        published_at: '2011-05-19T00:00:00.000Z',
      },
      {
        url: 'https://child.snuh.org/m/board/B051/view.do?bbs_no=7101&searchWord=%EB%8F%84%ED%86%A0%EB%A6%AC',
        title_original: '서울대학교어린이병원 소아암·희귀질환지원사업단 어린이날 행사',
        summary_original:
          '서울대학교어린이병원 소아암·희귀질환지원사업단은 치료 중인 어린이들에게 꿈과 희망을 전하기 위한 행사를 개최했습니다.',
        published_at: '2025-05-02T00:00:00.000Z',
      },
      {
        url: 'https://child.snuh.org/about/news/lecture/view.do?bbs_no=3500',
        title_original: '결절성경화증 공개강좌 안내',
        summary_original: '서울대학교병원은 결절성경화증 공개강좌를 개최해 희귀질환 관련 정보를 제공합니다.',
        published_at: '2014-07-11T00:00:00.000Z',
      },
    ],
  },
];

const sourceCountries = {
  'nord-news': { id: 'usa', name: '미국', code: '1', emoji: '🇺🇸', flagCode: 'us' },
  'global-genes': { id: 'usa', name: '미국', code: '1', emoji: '🇺🇸', flagCode: 'us' },
  'rare-disease-advisor': { id: 'usa', name: '미국', code: '1', emoji: '🇺🇸', flagCode: 'us' },
  'rare-x': { id: 'usa', name: '미국', code: '1', emoji: '🇺🇸', flagCode: 'us' },
  'everylife-foundation': { id: 'usa', name: '미국', code: '1', emoji: '🇺🇸', flagCode: 'us' },
  'patient-worthy': { id: 'usa', name: '미국', code: '1', emoji: '🇺🇸', flagCode: 'us' },
  'ncats-news': { id: 'usa', name: '미국', code: '1', emoji: '🇺🇸', flagCode: 'us' },
  'nih-reporter-rare-diseases': { id: 'usa', name: '미국', code: '1', emoji: '🇺🇸', flagCode: 'us' },
  'fda-rare-diseases': { id: 'usa', name: '미국', code: '1', emoji: '🇺🇸', flagCode: 'us' },
  'fda-orphan-products': { id: 'usa', name: '미국', code: '1', emoji: '🇺🇸', flagCode: 'us' },
  'eurordis-news': { id: 'europe', name: '유럽', code: 'EU', emoji: '🇪🇺', flagCode: 'eu' },
  'rare-diseases-international': { id: 'international', name: '국제', code: 'INT', emoji: '🌐' },
  'rare-disease-day': { id: 'international', name: '국제', code: 'INT', emoji: '🌐' },
  irdirc: { id: 'international', name: '국제', code: 'INT', emoji: '🌐' },
  'rare-revolution': { id: 'uk', name: '영국', code: '44', emoji: '🇬🇧', flagCode: 'gb' },
  'rare-voices-australia': { id: 'australia', name: '호주', code: '61', emoji: '🇦🇺', flagCode: 'au' },
  'cord-canada': { id: 'canada', name: '캐나다', code: '1', emoji: '🇨🇦', flagCode: 'ca' },
  'genetic-alliance-uk': { id: 'uk', name: '영국', code: '44', emoji: '🇬🇧', flagCode: 'gb' },
  'beacon-uk': { id: 'uk', name: '영국', code: '44', emoji: '🇬🇧', flagCode: 'gb' },
  'unique-rare-chromosome': { id: 'uk', name: '영국', code: '44', emoji: '🇬🇧', flagCode: 'gb' },
  'rare-disorders-nz': { id: 'newzealand', name: '뉴질랜드', code: '64', emoji: '🇳🇿', flagCode: 'nz' },
  'rare-diseases-south-africa': { id: 'southafrica', name: '남아공', code: '27', emoji: '🇿🇦', flagCode: 'za' },
  'raddar-japan': { id: 'japan', name: '일본', code: '81', emoji: '🇯🇵', flagCode: 'jp' },
  'shionogi-news': { id: 'japan', name: '일본', code: '81', emoji: '🇯🇵', flagCode: 'jp' },
  'shionogi-clinical-trials': { id: 'japan', name: '일본', code: '81', emoji: '🇯🇵', flagCode: 'jp' },
  'clinicaltrials-gov-rare-disease': { id: 'international', name: '국제', code: 'INT', emoji: '🌐' },
  'clinicaltrials-gov-orphan-drug': { id: 'international', name: '국제', code: 'INT', emoji: '🌐' },
  'google-news-rare-clinical-trials': { id: 'international', name: '국제', code: 'INT', emoji: '🌐' },
  'google-news-ppp2r5d': { id: 'international', name: '국제', code: 'INT', emoji: '🌐' },
  'known-ppp2r5d-trials': { id: 'japan', name: '일본', code: '81', emoji: '🇯🇵', flagCode: 'jp' },
  'feder-spain': { id: 'spain', name: '스페인', code: '34', emoji: '🇪🇸', flagCode: 'es' },
  'alliance-maladies-rares-france': { id: 'france', name: '프랑스', code: '33', emoji: '🇫🇷', flagCode: 'fr' },
  'uniamo-italy': { id: 'italy', name: '이탈리아', code: '39', emoji: '🇮🇹', flagCode: 'it' },
  'raredis-bulgaria': { id: 'bulgaria', name: '불가리아', code: '359', emoji: '🇧🇬', flagCode: 'bg' },
  'ema-whats-new': { id: 'europe', name: '유럽', code: 'EU', emoji: '🇪🇺', flagCode: 'eu' },
  'ema-rss-news': { id: 'europe', name: '유럽', code: 'EU', emoji: '🇪🇺', flagCode: 'eu' },
  'orphanet-news': { id: 'europe', name: '유럽', code: 'EU', emoji: '🇪🇺', flagCode: 'eu' },
  'orphanet-journal': { id: 'europe', name: '유럽', code: 'EU', emoji: '🇪🇺', flagCode: 'eu' },
  'ern-rnd': { id: 'europe', name: '유럽', code: 'EU', emoji: '🇪🇺', flagCode: 'eu' },
  'snuh-rare-disease-center': { id: 'korea', name: '대한민국', code: '82', emoji: '🇰🇷', flagCode: 'kr' },
  'snuh-child-lectures': { id: 'korea', name: '대한민국', code: '82', emoji: '🇰🇷', flagCode: 'kr' },
  'snuh-child-news': { id: 'korea', name: '대한민국', code: '82', emoji: '🇰🇷', flagCode: 'kr' },
  'kdca-search': { id: 'korea', name: '대한민국', code: '82', emoji: '🇰🇷', flagCode: 'kr' },
  'known-korea-rare-disease': { id: 'korea', name: '대한민국', code: '82', emoji: '🇰🇷', flagCode: 'kr' },
};

function getSourceCountry(sourceId) {
  return sourceCountries[sourceId] || { id: 'international', name: '국제', code: 'INT', emoji: '🌐' };
}

function withCountryMetadata(item) {
  const country = getSourceCountry(item.source_id);
  return {
    ...item,
    country_name: item.country_name || country.name,
    country_code: item.country_code || country.code,
    country_flag_code: item.country_flag_code || country.flagCode || null,
  };
}

const diseaseCategorySource = {
  id: 'orphanet-nomenclature',
  name: 'Orphanet Nomenclature',
  url: 'https://www.orphadata.com/data/xml/en_product1.xml',
};
const krdisBaseUrl = 'http://www.krdis.com';
const krdisDiseaseBoardUrl = `${krdisBaseUrl}/iboard/board.html`;

const rareDiseaseTerms = [
  'rare disease',
  'rare diseases',
  'orphan disease',
  'orphan diseases',
  'orphan drug',
  'orphan medicine',
  'orphan medicinal',
  'ultra-rare',
  'genetic disease',
  'genomic medicine',
  '희귀질환',
  '희귀 질환',
  '희귀병',
  '유전질환',
  '희귀의약품',
  '希少疾患',
  '難病',
  '稀少疾患',
  '小児慢性',
  'enfermedades raras',
  'enfermedad rara',
  'maladies rares',
  'maladie rare',
  'seltene erkrankungen',
  'seltene krankheit',
  'malattie rare',
  'malattia rara',
  'doenças raras',
  'doença rara',
  'doencas raras',
];

const keywordAliases = [
  { keyword: 'ppp2r5d', terms: ['ppp2r5d', 'jordan syndrome', 'jordans syndrome'] },
  { keyword: 'orphan drug', terms: ['orphan drug', 'orphan medicine', 'orphan designation'] },
  { keyword: 'gene therapy', terms: ['gene therapy', 'genetic therapy'] },
  { keyword: 'clinical trial', terms: ['clinical trial', 'trial', 'study'] },
  { keyword: 'diagnosis', terms: ['diagnosis', 'diagnostic', 'screening'] },
  { keyword: 'policy', terms: ['policy', 'regulation', 'legislation'] },
  { keyword: 'patient advocacy', terms: ['patient advocacy', 'advocacy', 'patient organisation', 'patient organization'] },
];

const clinicalTrialTerms = [
  'clinical trial',
  'clinicaltrials.gov',
  'phase 1',
  'phase 2',
  'phase 3',
  'randomized',
  'double-blind',
  'placebo-controlled',
  'open-label',
  'enrolling',
  'participants',
  'investigational',
  'pipeline',
  'drug study',
  'orphan drug',
  'orphan designation',
  '임상시험',
  '임상 시험',
  '치료제 개발',
  '희귀의약품',
];

const diseaseSearchEnhancements = [
  {
    matchTerms: ['ppp2r5d', 'jordan syndrome', 'jordans syndrome', 'houge-janssens'],
    gene_symbols: ['PPP2R5D'],
    name_en: 'PPP2R5D-related neurodevelopmental disorder',
    name_ko: '지적장애-대두증-근긴장저하-행동이상 증후군',
    aliases: [
      'Jordan syndrome',
      "Jordan's syndrome",
      'PPP2R5D-related intellectual disability',
      'Houge-Janssens syndrome 1',
    ],
  },
];

function normalizeText(value = '') {
  return value.replace(/\s+/g, ' ').trim();
}

function formatError(error) {
  if (error instanceof Error) return error.message;
  if (typeof error === 'object' && error !== null) {
    return error.message || error.msg || JSON.stringify(error);
  }
  return String(error);
}

function isMissingTableError(error) {
  return formatError(error).toLowerCase().includes("could not find the table 'public.news_articles'");
}

async function readStoredNews() {
  try {
    const raw = await fs.readFile(newsStorePath, 'utf8');
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

async function writeStoredNews(rows) {
  await fs.mkdir(dataDir, { recursive: true });
  await fs.writeFile(newsStorePath, JSON.stringify(rows, null, 2));
}

async function upsertFileNews(rows) {
  const current = await readStoredNews();
  const merged = new Map(current.map((item) => [item.url, item]));

  for (const row of rows) {
    merged.set(row.url, {
      id: row.id || row.url,
      created_at: row.created_at || new Date().toISOString(),
      ...merged.get(row.url),
      ...row,
    });
  }

  const nextRows = Array.from(merged.values()).sort((a, b) => {
    const first = new Date(a.published_at || a.crawled_at || 0).getTime();
    const second = new Date(b.published_at || b.crawled_at || 0).getTime();
    return second - first;
  });

  await writeStoredNews(nextRows);
  return nextRows.length;
}

async function readScheduleStore() {
  try {
    const raw = await fs.readFile(scheduleStorePath, 'utf8');
    const parsed = JSON.parse(raw);
    return {
      entries: Array.isArray(parsed.entries) ? parsed.entries : [],
      shares: Array.isArray(parsed.shares) ? parsed.shares : [],
    };
  } catch {
    return { entries: [], shares: [] };
  }
}

async function writeScheduleStore(store) {
  await fs.mkdir(dataDir, { recursive: true });
  await fs.writeFile(scheduleStorePath, JSON.stringify(store, null, 2));
}

async function getRequestUser(request) {
  if (!adminSupabase) return null;
  const token = request.get('authorization')?.replace(/^Bearer\s+/i, '');
  if (!token) return null;
  const { data, error } = await adminSupabase.auth.getUser(token);
  if (error) return null;
  return data.user ?? null;
}

async function requireUser(request, response) {
  const user = await getRequestUser(request);
  if (!user) {
    response.status(401).json({ error: 'Unauthorized' });
    return null;
  }
  return user;
}

async function getProfilesById(ids) {
  const uniqueIds = Array.from(new Set(ids.filter(Boolean)));
  if (!adminSupabase || uniqueIds.length === 0) return new Map();
  const { data } = await adminSupabase.from('profiles').select('id,nickname,full_name').in('id', uniqueIds);
  return new Map((data ?? []).map((profile) => [profile.id, profile]));
}

function absolutizeUrl(href, baseUrl) {
  try {
    return new URL(href, baseUrl).toString();
  } catch {
    return '';
  }
}

function isRelevant(item, source) {
  if (source.alwaysRelevant) return true;
  const haystack = `${item.title_original || ''} ${item.summary_original || ''} ${item.url || ''}`.toLowerCase();
  return rareDiseaseTerms.some((term) => haystack.includes(term.toLowerCase()));
}

function stripTags(html = '') {
  return normalizeText(html.replace(/<[^>]*>/g, ' '));
}

function decodeHtmlEntities(value = '') {
  return normalizeText(
    value
      .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
      .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCodePoint(parseInt(code, 16)))
      .replace(/&nbsp;/g, ' ')
      .replace(/&amp;/g, '&')
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/&apos;/g, "'")
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>'),
  );
}

function cleanKrdisText(value = '') {
  return normalizeText(
    value
      .replace(/\u00a0/g, ' ')
      .replace(/\r/g, '\n')
      .replace(/function\s+PhotoViewJS\s*\([^]*?\}\s*/gi, ' ')
      .replace(/CenterOpen\s*\([^)]*\)\s*;?/gi, ' ')
      .replace(/\n{3,}/g, '\n\n'),
  );
}

function extractGeneSymbols(value = '') {
  const blocked = new Set(['DNA', 'RNA', 'KCD', 'KID', 'ORPHA', 'KRDIS']);
  const matches = value.match(/\b[A-Z][A-Z0-9]{2,12}(?:-[A-Z0-9]{2,12})?\b/g) ?? [];
  return Array.from(new Set(matches.filter((match) => !blocked.has(match) && /[0-9]/.test(match))));
}

function getDiseaseSearchEnhancement(value = '') {
  const haystack = normalizeText(value).toLowerCase();
  return diseaseSearchEnhancements.find((item) => item.matchTerms.some((term) => haystack.includes(term)));
}

function applyDiseaseSearchEnhancements(item, query = '') {
  const enhancement = getDiseaseSearchEnhancement([
    query,
    item.name_ko,
    item.name_en,
    item.category,
    item.kcd_code,
    ...(item.gene_symbols ?? []),
  ].filter(Boolean).join(' '));
  if (!enhancement) return item;

  return {
    ...item,
    name_ko: item.name_ko || enhancement.name_ko,
    name_en: item.name_en || enhancement.name_en,
    gene_symbols: Array.from(new Set([...(item.gene_symbols ?? []), ...enhancement.gene_symbols])),
    aliases: enhancement.aliases,
  };
}

function normalizeArticleBody(value = '') {
  return value
    .replace(/&#8230;/g, '...')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\r/g, '')
    .split('\n')
    .map((line) => normalizeText(line))
    .filter(Boolean)
    .join('\n\n');
}

function parsePublishedAt(value) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

function isGenericLinkTitle(title = '') {
  return /^(continue reading|read more|learn more|more|자세히 보기|더 보기|계속 읽기)$/i.test(normalizeText(title));
}

function titleFromUrl(url = '') {
  try {
    const slug = new URL(url).pathname.split('/').filter(Boolean).pop() || '';
    return normalizeText(
      slug
        .replace(/\.(html?|php)$/i, '')
        .replace(/[-_]+/g, ' ')
        .replace(/\b\w/g, (letter) => letter.toUpperCase()),
    );
  } catch {
    return '';
  }
}

function firstArray(value) {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

async function fetchText(url) {
  const response = await fetch(url, {
    headers: {
      accept: 'text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8',
      'user-agent': 'RareCareKoreaBot/1.0 (+https://rered-production.up.railway.app/)',
    },
    signal: AbortSignal.timeout(requestTimeoutMs),
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  return response.text();
}

async function fetchKrdisHtml(url) {
  const response = await fetch(url, {
    headers: {
      accept: 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
      'user-agent': 'Mozilla/5.0 RareCareKoreaBot/1.0 (+https://rered-production.up.railway.app/)',
    },
    signal: AbortSignal.timeout(Math.max(requestTimeoutMs, 18000)),
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  return response.text();
}

async function fetchReaderText(url) {
  const readerUrl = `${readerFallbackBaseUrl}${url}`;
  const response = await fetch(readerUrl, {
    headers: {
      accept: 'text/plain,*/*;q=0.8',
      'user-agent': 'RareCareKoreaBot/1.0 (+https://rered-production.up.railway.app/)',
    },
    signal: AbortSignal.timeout(Math.max(requestTimeoutMs, 20000)),
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  return response.text();
}

function parseRss(xml, source) {
  const parser = new XMLParser({
    ignoreAttributes: false,
    removeNSPrefix: true,
  });
  const parsed = parser.parse(xml);
  const channelItems = firstArray(parsed?.rss?.channel?.item);
  const feedItems = firstArray(parsed?.feed?.entry);

  return [...channelItems, ...feedItems].map((item) => {
    const link = typeof item.link === 'string' ? item.link : item.link?.href;
    return {
      source_id: source.id,
      source_name: source.name,
      source_url: source.url,
      news_category: source.news_category || null,
      url: absolutizeUrl(link || item.guid || item.id || '', source.baseUrl || source.url),
      title_original: normalizeText(item.title || ''),
      summary_original: stripTags(item.description || item.summary || item.content || ''),
      published_at: parsePublishedAt(item.pubDate || item.published || item.updated),
    };
  });
}

function parseDiseaseCategories(xml) {
  const parser = new XMLParser({
    ignoreAttributes: false,
    removeNSPrefix: true,
  });
  const parsed = parser.parse(xml);
  const disorders = firstArray(parsed?.JDBOR?.DisorderList?.Disorder);

  return disorders
    .map((disorder) => ({
      orpha_code: normalizeText(String(disorder.OrphaCode || '')),
      name_en: normalizeText(typeof disorder.Name === 'string' ? disorder.Name : disorder.Name?.['#text'] || ''),
      name_ko: null,
      source: 'orphanet',
      source_url: diseaseCategorySource.url,
      synced_at: new Date().toISOString(),
    }))
    .filter((category) => category.orpha_code && category.name_en);
}

function parseKrdisDiseaseSearch(html) {
  const $ = cheerio.load(html);
  const results = [];
  const seen = new Set();

  $('.board_list tbody tr a[href*="mode=view"][href*="code=bbs_004"]').each((_, element) => {
    const row = $(element).closest('tr');
    const cells = row.find('td');
    const href = $(element).attr('href') || '';
    const title = cleanKrdisText($(element).attr('title') || '');
    const text = cleanKrdisText($(element).text());
    const englishName = cleanKrdisText($(element).find('.tcolor_blue').first().text());
    const koreanName = title || cleanKrdisText(text.replace(englishName, ''));
    const category = cleanKrdisText(cells.eq(2).text());
    const kcdCode = cleanKrdisText(cells.eq(3).text());
    const url = absolutizeUrl(href, krdisBaseUrl);

    if (!url || seen.has(url) || (!koreanName && !englishName)) return;
    seen.add(url);
    results.push(applyDiseaseSearchEnhancements({
      id: url,
      name_ko: koreanName,
      name_en: englishName || null,
      category: category && category !== '없음' ? category : null,
      kcd_code: kcdCode && kcdCode !== '없음' ? kcdCode : null,
      gene_symbols: extractGeneSymbols(`${koreanName} ${englishName}`),
      url,
      source: 'KRDIS',
    }, `${koreanName} ${englishName}`));
  });

  return results.slice(0, 30);
}

function parseKrdisDiseaseDetail(html, fallbackUrl) {
  const $ = cheerio.load(html);
  $('script, style').remove();
  const titleArea = $('.diseaseT').first();
  const nameKo = cleanKrdisText(titleArea.find('.dt').text().replace(/^질환명\s*:\s*/i, ''));
  const nameEn = cleanKrdisText(titleArea.find('.eng .tcolor_blue').first().text());
  const kidCode = cleanKrdisText(titleArea.find('.code').text().replace(/^KID\s*코드명\s*:\s*/i, ''));
  const sections = [];

  $('.diseaseTable tr th').each((_, heading) => {
    const $heading = $(heading);
    const englishTitle = cleanKrdisText($heading.find('span').first().text());
    const koreanTitle = cleanKrdisText($heading.clone().children('span').remove().end().text());
    const bodyCell = $heading.closest('tr').next('tr').find('td').first();
    bodyCell.find('script, style, noscript').remove();
    const body = cleanKrdisText(bodyCell.text());

    if (!koreanTitle || !body) return;
    sections.push({
      title_ko: koreanTitle,
      title_en: englishTitle || null,
      body,
    });
  });

  return {
    name_ko: nameKo || null,
    name_en: nameEn || null,
    kid_code: kidCode || null,
    gene_symbols: extractGeneSymbols(`${nameKo} ${nameEn} ${sections.map((section) => section.body).join(' ')}`),
    sections,
    source: 'KRDIS',
    source_url: fallbackUrl,
  };
}

async function searchKrdisDiseases(query) {
  const body = new URLSearchParams({
    ad_mode: 'search',
    search: 'yes',
    code: 'bbs_004',
    field: 'all',
    s_que: query,
  });
  const response = await fetch(`${krdisDiseaseBoardUrl}?openType=&&code=bbs_004&mode=`, {
    method: 'POST',
    headers: {
      accept: 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
      'content-type': 'application/x-www-form-urlencoded',
      'user-agent': 'Mozilla/5.0 RareCareKoreaBot/1.0 (+https://rered-production.up.railway.app/)',
    },
    body,
    signal: AbortSignal.timeout(Math.max(requestTimeoutMs, 18000)),
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  const html = await response.text();
  const normalizedQuery = normalizeText(query).toLowerCase();
  const shouldFilterStrictly = /^[a-z0-9-]{2,}$/i.test(normalizedQuery);
  const results = parseKrdisDiseaseSearch(html).map((item) => applyDiseaseSearchEnhancements(item, query));

  if (!shouldFilterStrictly) return results;

  return results.filter((item) =>
    [item.name_ko, item.name_en, item.category, item.kcd_code, ...(item.gene_symbols ?? []), ...(item.aliases ?? [])]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
      .includes(normalizedQuery),
  );
}

async function getKrdisDiseaseDetail(url) {
  const parsedUrl = new URL(url);
  if (parsedUrl.hostname !== 'www.krdis.com' || !parsedUrl.pathname.includes('/iboard/board.html')) {
    throw new Error('KRDIS disease detail URL is invalid.');
  }

  const html = await fetchKrdisHtml(parsedUrl.toString());
  return parseKrdisDiseaseDetail(html, parsedUrl.toString());
}

async function syncDiseaseCategories() {
  if (!adminSupabase) {
    throw new Error('Supabase service key is not configured.');
  }

  const raw = await fetchText(diseaseCategorySource.url);
  const categories = parseDiseaseCategories(raw);

  for (let index = 0; index < categories.length; index += 500) {
    const chunk = categories.slice(index, index + 500);
    const { error } = await adminSupabase.from('disease_categories').upsert(chunk, {
      onConflict: 'orpha_code',
    });
    if (error) throw error;
  }

  return { inserted_or_updated: categories.length };
}

function parseHtml(html, source) {
  const $ = cheerio.load(html);
  const items = new Map();

  $(source.itemSelector).each((_, element) => {
    const title = normalizeText($(element).text());
    const href = $(element).attr('href');
    const url = absolutizeUrl(href || '', source.baseUrl || source.url);
    if (!title || !url || title.length < 8) return;
    const container = $(element).closest(
      'article, li, .views-row, .card, .teaser, .news-listing__item, .search-result, .post, .node, .views-field',
    );
    const summary = normalizeText(
      container.find('p, .summary, .description, .excerpt, .field--name-body').first().text(),
    );
    const publishedAt =
      container.find('time').first().attr('datetime') ||
      container.find('[datetime]').first().attr('datetime') ||
      normalizeText(container.find('time, .date, .posted-on, .field--name-created').first().text()) ||
      null;

    items.set(url, {
      source_id: source.id,
      source_name: source.name,
      source_url: source.url,
      news_category: source.news_category || null,
      url,
      title_original: title,
      summary_original: summary,
      published_at: parsePublishedAt(publishedAt),
    });
  });

  return Array.from(items.values());
}

function formatClinicalTrialDate(dateStruct) {
  if (!dateStruct?.date) return '';
  return dateStruct.type ? `${dateStruct.date} (${dateStruct.type})` : dateStruct.date;
}

function parseClinicalTrialsGov(studies, source) {
  return studies
    .map((study) => {
      const protocol = study.protocolSection || {};
      const identification = protocol.identificationModule || {};
      const status = protocol.statusModule || {};
      const design = protocol.designModule || {};
      const conditions = protocol.conditionsModule?.conditions || [];
      const interventions = protocol.armsInterventionsModule?.interventions || [];
      const sponsor = protocol.sponsorCollaboratorsModule?.leadSponsor?.name || '';
      const nctId = identification.nctId;
      const interventionNames = interventions
        .filter((intervention) =>
          ['DRUG', 'BIOLOGICAL', 'GENETIC', 'COMBINATION_PRODUCT', 'DIETARY_SUPPLEMENT'].includes(
            String(intervention.type || '').toUpperCase(),
          ),
        )
        .map((intervention) => normalizeText(intervention.name || ''))
        .filter(Boolean);
      const phases = (design.phases || []).filter((phase) => phase && phase !== 'NA');
      const title = normalizeText(identification.briefTitle || identification.officialTitle || '');
      if (interventionNames.length === 0 && phases.length === 0) return null;
      const statusText = normalizeText(status.overallStatus || '').replace(/_/g, ' ');
      const summaryParts = [
        `Status: ${statusText || 'unknown'}`,
        phases.length > 0 ? `Phase: ${phases.join(', ')}` : '',
        conditions.length > 0 ? `Condition: ${conditions.slice(0, 4).join(', ')}` : '',
        interventionNames.length > 0 ? `Investigational treatment: ${interventionNames.slice(0, 5).join(', ')}` : '',
        sponsor ? `Sponsor: ${sponsor}` : '',
        formatClinicalTrialDate(status.startDateStruct) ? `Start: ${formatClinicalTrialDate(status.startDateStruct)}` : '',
        formatClinicalTrialDate(status.completionDateStruct)
          ? `Completion: ${formatClinicalTrialDate(status.completionDateStruct)}`
          : '',
        protocol.descriptionModule?.briefSummary || '',
      ].filter(Boolean);

      return {
        source_id: source.id,
        source_name: source.name,
        source_url: source.url,
        news_category: 'clinical_trial',
        url: nctId ? `https://clinicaltrials.gov/study/${nctId}` : '',
        title_original: title,
        summary_original: summaryParts.join('\n\n'),
        content_original: summaryParts.join('\n\n'),
        published_at: parsePublishedAt(
          status.lastUpdatePostDateStruct?.date ||
            status.studyFirstPostDateStruct?.date ||
            status.lastUpdateSubmitDate ||
            status.studyFirstSubmitDate,
        ),
      };
    })
    .filter((item) => item?.url && item.title_original);
}

async function parseWordPressSource(source) {
  const perPage = Math.min(Number(source.perPage || 100), 100);
  const maxItems = Number(source.maxItems || maxItemsPerSource);
  const maxPages = Math.max(1, Math.ceil(maxItems / perPage));
  const rows = [];

  for (let page = 1; page <= maxPages && rows.length < maxItems; page += 1) {
    const url = new URL(source.url);
    url.searchParams.set('per_page', String(perPage));
    url.searchParams.set('page', String(page));
    url.searchParams.set('_fields', 'date,link,title,excerpt,content');

    const response = await fetch(url, {
      headers: {
        accept: 'application/json',
        'user-agent': 'Mozilla/5.0 RareCareKorea/1.0 (contact: askipgh@gmail.com)',
      },
      signal: AbortSignal.timeout(Math.max(requestTimeoutMs, 20000)),
    });

    if (response.status === 400 || response.status === 404) break;
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);

    const payload = await response.json();
    if (!Array.isArray(payload) || payload.length === 0) break;

    for (const post of payload) {
      const title = decodeHtmlEntities(stripTags(post.title?.rendered || ''));
      const summary = decodeHtmlEntities(stripTags(post.excerpt?.rendered || post.content?.rendered || ''));
      const content = decodeHtmlEntities(stripTags(post.content?.rendered || post.excerpt?.rendered || ''));
      if (!post.link || !title) continue;
      rows.push({
        source_id: source.id,
        source_name: source.name,
        source_url: source.url,
        news_category: source.news_category || null,
        url: post.link,
        title_original: title,
        summary_original: summary || title,
        content_original: content || summary || title,
        published_at: parsePublishedAt(post.date),
      });
      if (rows.length >= maxItems) break;
    }
  }

  return rows;
}

function getClinicalTrialBackfillFilter(years = clinicalTrialBackfillYears) {
  const cutoffYear = new Date().getUTCFullYear() - Math.max(1, years);
  return `AREA[StudyType]Interventional AND AREA[StudyFirstPostDate]RANGE[${cutoffYear}-01-01,MAX]`;
}

async function parseClinicalTrialsSource(source, options = {}) {
  const pageSize = Math.min(Number(options.pageSize || maxItemsPerSource), 100);
  const maxPages = Math.max(1, Number(options.maxPages || 1));
  const rows = [];
  let nextPageToken = '';

  for (let page = 0; page < maxPages; page += 1) {
    const url = new URL(source.url);
    for (const [key, value] of Object.entries(source.query || {})) {
      url.searchParams.set(key, value);
    }
    if (options.query) {
      for (const [key, value] of Object.entries(options.query)) {
        url.searchParams.set(key, value);
      }
    }
    if (nextPageToken) url.searchParams.set('pageToken', nextPageToken);
    url.searchParams.set('pageSize', String(pageSize));
    url.searchParams.set('format', 'json');

    const response = await fetch(url, {
      headers: {
        accept: 'application/json',
        'user-agent': 'Mozilla/5.0 RareCareKorea/1.0 (contact: askipgh@gmail.com)',
      },
      signal: AbortSignal.timeout(Math.max(requestTimeoutMs, 20000)),
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    if (!response.headers.get('content-type')?.includes('application/json')) {
      throw new Error(`Unexpected ClinicalTrials.gov response: ${response.headers.get('content-type') || 'unknown content type'}`);
    }
    const payload = await response.json();
    rows.push(...parseClinicalTrialsGov(payload.studies || [], source));
    nextPageToken = payload.nextPageToken || '';
    if (!nextPageToken) break;
  }

  return rows;
}

function plainMarkdownLine(line = '') {
  return normalizeText(
    line
      .replace(/!\[[^\]]*]\([^)]+\)/g, ' ')
      .replace(/\[([^\]]+)]\([^)]+\)/g, '$1')
      .replace(/^#{1,6}\s*/, '')
      .replace(/^\*\s+/, '')
      .replace(/\*\*/g, '')
      .replace(/\s+/g, ' '),
  );
}

function isReaderBoilerplate(line = '') {
  return /^(we value your privacy|we use cookies|by continuing to use this website|customize|reject all|accept all|necessary|functional|analytics|advertisement|cookie|duration|description|keyword search|tags|set valu|share|subscribe|donate|contact us|privacy policy|terms)/i.test(
    line,
  );
}

function extractReaderDetails(markdown, expectedTitle = '') {
  const metadata = {};
  const publishedMatch = markdown.match(/^Published Time:\s*(.+)$/im);
  if (publishedMatch) metadata.publishedAt = parsePublishedAt(publishedMatch[1]);

  const contentStart = markdown.indexOf('Markdown Content:');
  const body = contentStart >= 0 ? markdown.slice(contentStart + 'Markdown Content:'.length) : markdown;
  const lines = body
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

  const expectedWords = normalizeText(expectedTitle)
    .toLowerCase()
    .split(/\s+/)
    .filter((word) => word.length > 4)
    .slice(0, 8);
  let startIndex = -1;

  lines.forEach((line, index) => {
    if (!line.startsWith('#')) return;
    const clean = plainMarkdownLine(line).toLowerCase();
    const matches = expectedWords.length > 0 ? expectedWords.filter((word) => clean.includes(word)).length : 0;
    if (matches >= Math.min(3, expectedWords.length || 3)) startIndex = index;
  });

  if (startIndex < 0) startIndex = lines.findIndex((line) => line.startsWith('#'));

  const title = startIndex >= 0 ? plainMarkdownLine(lines[startIndex]).replace(/\s+-\s+.*$/, '') : '';
  const paragraphs = [];

  for (const rawLine of lines.slice(Math.max(0, startIndex + 1))) {
    const line = plainMarkdownLine(rawLine);
    if (!line || isReaderBoilerplate(line)) continue;
    if (/^posted\s+/i.test(line) || /^categorized in/i.test(line)) continue;
    if (/^(advocacy|featured news|industry|research|statements)$/i.test(line)) continue;
    if (paragraphs.length >= 2 && /^\[[^\]]+]\([^)]+\)$/.test(rawLine)) break;
    if (paragraphs.length >= 2 && /^more than|^related|^previous|^next/i.test(line)) break;
    if (line.length < 45) continue;
    paragraphs.push(line);
    if (paragraphs.length >= 30) break;
  }

  return {
    title,
    summary: paragraphs[0] || '',
    content: normalizeArticleBody(paragraphs.join('\n\n')),
    publishedAt: metadata.publishedAt,
  };
}

function extractArticleDetails(html) {
  const $ = cheerio.load(html);
  $('script, style, noscript, iframe, nav, header, footer, aside, form, button, .cookie, .cookies, .sidebar, .menu').remove();
  const title = normalizeText(
    $('meta[property="og:title"]').attr('content') ||
      $('meta[name="twitter:title"]').attr('content') ||
      $('h1').first().text(),
  );
  const summary = normalizeText(
    $('meta[name="description"]').attr('content') ||
      $('meta[property="og:description"]').attr('content') ||
      $('article p, main p, .content p').first().text(),
  );
  const contentSelectors = [
    'article',
    'main article',
    'main .content',
    '.entry-content',
    '.post-content',
    '.field--name-body',
    '.node__content',
    '.article-body',
    '.news-body',
    '.press-release',
    '[itemprop="articleBody"]',
    'main',
  ];
  const candidates = contentSelectors
    .map((selector) => {
      const paragraphs = $(selector)
        .find('p, li')
        .map((_, element) => normalizeText($(element).text()))
        .get()
        .filter((paragraph) => paragraph.length > 40)
        .filter((paragraph, index, all) => all.indexOf(paragraph) === index);
      return { selector, paragraphs, length: paragraphs.join(' ').length };
    })
    .filter((candidate) => candidate.length > 0)
    .sort((a, b) => b.length - a.length);
  const fallbackParagraphs = $('p')
    .map((_, element) => normalizeText($(element).text()))
    .get();
  const paragraphs = (candidates[0]?.paragraphs || fallbackParagraphs)
    .filter((paragraph) => paragraph.length > 40)
    .filter((paragraph, index, all) => all.indexOf(paragraph) === index)
    .slice(0, 40);
  const content = normalizeArticleBody(paragraphs.join('\n\n'));
  const publishedAt = parsePublishedAt(
    $('meta[property="article:published_time"]').attr('content') ||
      $('time').first().attr('datetime') ||
      $('[datetime]').first().attr('datetime') ||
      normalizeText($('time, .date, .posted-on').first().text()),
  );

  return { title, summary, content, publishedAt };
}

async function fetchArticleDetails(url, expectedTitle = '') {
  let htmlDetails = null;
  try {
    const raw = await fetchText(url);
    htmlDetails = extractArticleDetails(raw);
    if (normalizeArticleBody(htmlDetails.content || '').length >= minCachedArticleContentLength) {
      return htmlDetails;
    }
  } catch (error) {
    htmlDetails = null;
  }

  try {
    const readerText = await fetchReaderText(url);
    const readerDetails = extractReaderDetails(readerText, expectedTitle || htmlDetails?.title || '');
    if (normalizeArticleBody(readerDetails.content || '').length > normalizeArticleBody(htmlDetails?.content || '').length) {
      return {
        title: readerDetails.title || htmlDetails?.title || '',
        summary: readerDetails.summary || htmlDetails?.summary || '',
        content: readerDetails.content,
        publishedAt: readerDetails.publishedAt || htmlDetails?.publishedAt || null,
      };
    }
  } catch (error) {
    if (!htmlDetails) throw error;
  }

  return htmlDetails || { title: '', summary: '', content: '', publishedAt: null };
}

async function enrichItem(item) {
  const hasEnoughCachedContent = normalizeArticleBody(item.content_original || '').length >= minCachedArticleContentLength;
  if (item.summary_original && hasEnoughCachedContent && item.published_at && !isGenericLinkTitle(item.title_original)) return item;

  try {
    const details = await fetchArticleDetails(item.url, item.title_original);
    const fallbackTitle = isGenericLinkTitle(item.title_original) ? titleFromUrl(item.url) : item.title_original;
    const existingContent = normalizeArticleBody(item.content_original || '');
    const fetchedContent = normalizeArticleBody(details.content || '');
    const contentOriginal =
      fetchedContent.length > existingContent.length
        ? fetchedContent
        : existingContent || normalizeArticleBody(details.summary || item.summary_original || '');
    return {
      ...item,
      title_original: details.title || fallbackTitle || item.title_original,
      summary_original: item.summary_original || details.summary,
      content_original: contentOriginal,
      published_at: item.published_at || details.publishedAt,
    };
  } catch {
    return {
      ...item,
      title_original: isGenericLinkTitle(item.title_original) ? titleFromUrl(item.url) || item.title_original : item.title_original,
      content_original: item.content_original || item.summary_original || '',
    };
  }
}

function extractKeywords(item) {
  const haystack = normalizeText(
    `${item.source_name || ''} ${item.title_original || ''} ${item.summary_original || ''} ${item.title_ko || ''} ${
      item.summary_ko || ''
    }`,
  );
  const lower = haystack.toLowerCase();
  const keywords = new Set();

  for (const alias of keywordAliases) {
    if (alias.terms.some((term) => lower.includes(term))) {
      keywords.add(alias.keyword);
    }
  }

  for (const term of rareDiseaseTerms) {
    if (lower.includes(term.toLowerCase())) {
      keywords.add(term.toLowerCase());
    }
  }

  const geneTokens = haystack.match(/\b[A-Z][A-Z0-9]{2,}[A-Z0-9-]*\b/g) || [];
  for (const token of geneTokens) {
    if (token.length <= 24 && !['FDA', 'EMA', 'NIH', 'NORD', 'COVID'].includes(token)) {
      keywords.add(token.toLowerCase());
    }
  }

  const diseaseTokens = haystack.match(/\b[A-Za-z0-9-]+(?: syndrome| disease| disorder| deficiency| ataxia)\b/gi) || [];
  for (const token of diseaseTokens) {
    keywords.add(token.toLowerCase());
  }

  keywords.add(`source:${item.source_id}`);
  return Array.from(keywords).slice(0, 40);
}

function classifyNewsCategory(item) {
  if (item.news_category) return item.news_category;
  if (item.source_id === 'known-ppp2r5d-trials' || item.source_id === 'shionogi-clinical-trials') return 'clinical_trial';

  const haystack = normalizeText(
    `${item.source_name || ''} ${item.url || ''} ${item.title_original || ''} ${item.summary_original || ''} ${
      item.content_original || ''
    } ${item.title_ko || ''} ${item.summary_ko || ''} ${item.content_ko || ''} ${(item.keywords || []).join(' ')}`,
  ).toLowerCase();

  return clinicalTrialTerms.some((term) => haystack.includes(term.toLowerCase())) ? 'clinical_trial' : 'general';
}

async function translateToKorean(text) {
  const trimmed = normalizeText(text);
  if (!trimmed) return '';
  if (/[가-힣]/.test(trimmed)) return trimmed;

  try {
    const url = new URL('https://api.mymemory.translated.net/get');
    url.searchParams.set('q', trimmed.slice(0, 500));
    url.searchParams.set('langpair', 'en|ko');
    const response = await fetch(url, { signal: AbortSignal.timeout(requestTimeoutMs) });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const data = await response.json();
    const translated = normalizeText(data?.responseData?.translatedText || '');
    if (translated && translated !== trimmed && /[가-힣]/.test(translated)) return translated;
  } catch {
    // Try the next public endpoint below.
  }

  try {
    const url = new URL('https://translate.googleapis.com/translate_a/single');
    url.searchParams.set('client', 'gtx');
    url.searchParams.set('sl', 'auto');
    url.searchParams.set('tl', 'ko');
    url.searchParams.set('dt', 't');
    url.searchParams.set('q', trimmed.slice(0, 500));
    const response = await fetch(url, { signal: AbortSignal.timeout(requestTimeoutMs) });
    if (!response.ok) return trimmed;
    const data = await response.json();
    const translated = normalizeText(data?.[0]?.map((part) => part?.[0] || '').join('') || '');
    return translated || trimmed;
  } catch {
    return trimmed;
  }
}

async function translateLongTextToKorean(text) {
  const normalized = normalizeArticleBody(text);
  if (!normalized) return '';
  if (/[가-힣]/.test(normalized)) return normalized;

  const paragraphs = normalized.split(/\n{2,}/);
  const chunks = [];
  let current = '';

  for (const paragraph of paragraphs) {
    if ((current + '\n\n' + paragraph).trim().length > 450 && current) {
      chunks.push(current);
      current = paragraph;
    } else {
      current = [current, paragraph].filter(Boolean).join('\n\n');
    }
  }
  if (current) chunks.push(current);

  const translatedChunks = [];
  for (const chunk of chunks.slice(0, 12)) {
    translatedChunks.push(await translateToKorean(chunk));
  }

  return normalizeArticleBody(translatedChunks.join('\n\n'));
}

async function collectSource(source) {
  const items =
    source.type === 'seed'
      ? source.items.map((item) => ({
          source_id: source.id,
          source_name: source.name,
          source_url: item.url,
          news_category: source.news_category || item.news_category || null,
          ...item,
        }))
      : source.type === 'clinicaltrials'
        ? await parseClinicalTrialsSource(source)
        : source.type === 'wordpress'
          ? await parseWordPressSource(source)
          : source.type === 'rss'
            ? parseRss(await fetchText(source.url), source)
            : parseHtml(await fetchText(source.url), source);
  const candidates = items
    .filter((item) => item.url && item.title_original && isRelevant(item, source))
    .slice(0, Number(source.maxItems || maxItemsPerSource));
  const enriched = [];

  for (const item of candidates) {
    enriched.push(source.type === 'clinicaltrials' ? item : await enrichItem(item));
  }

  return enriched.filter((item) => item.url && item.title_original && isRelevant(item, source));
}

async function persistNewsRows(rows) {
  if (rows.length === 0) return 'none';

  if (!adminSupabase) {
    await upsertFileNews(
      rows.map((row) => ({
        ...withCountryMetadata(row),
        news_category: classifyNewsCategory(row),
      })),
    );
    return 'file';
  }

  const rowsWithCountries = rows.map(withCountryMetadata);
  const rowsWithMetadata = rowsWithCountries.map((row) => ({
    ...row,
    news_category: classifyNewsCategory(row),
  }));
  const { error } = await adminSupabase.from('news_articles').upsert(rowsWithMetadata, {
    onConflict: 'url',
  });
  if (error) {
    if (isMissingTableError(error)) {
      await upsertFileNews(rows);
      return 'file';
    }

    const errorText = formatError(error).toLowerCase();

    if (errorText.includes('news_category') || errorText.includes('country_')) {
      const rowsWithoutNewColumns = rowsWithMetadata.map(
        ({ news_category: _newsCategory, country_name: _countryName, country_code: _countryCode, country_flag_code: _countryFlagCode, ...row }) =>
          row,
      );
      const retry = await adminSupabase.from('news_articles').upsert(rowsWithoutNewColumns, {
        onConflict: 'url',
      });
      if (retry.error) {
        if (isMissingTableError(retry.error)) {
          await upsertFileNews(rows);
          return 'file';
        }
        const retryText = formatError(retry.error).toLowerCase();
        if (retryText.includes('keywords') || retryText.includes('content_ko') || retryText.includes('content_original')) {
          const rowsWithoutContentColumns = rowsWithoutNewColumns.map(
            ({ keywords: _keywords, content_original: _contentOriginal, content_ko: _contentKo, ...row }) => row,
          );
          const finalRetry = await adminSupabase.from('news_articles').upsert(rowsWithoutContentColumns, {
            onConflict: 'url',
          });
          if (finalRetry.error) throw finalRetry.error;
          return 'supabase';
        }
        throw retry.error;
      }
      return 'supabase';
    }

    if (errorText.includes('keywords') || errorText.includes('content_ko') || errorText.includes('content_original')) {
      const rowsWithoutContentColumns = rowsWithCountries.map(
        ({ keywords: _keywords, content_original: _contentOriginal, content_ko: _contentKo, ...row }) => row,
      );
      const retry = await adminSupabase.from('news_articles').upsert(rowsWithoutContentColumns, {
        onConflict: 'url',
      });
      if (retry.error) throw retry.error;
      return 'supabase';
    }

    throw error;
  }

  return 'supabase';
}

async function getExistingNewsUrls(urls) {
  const uniqueUrls = Array.from(new Set(urls.filter(Boolean)));
  const existing = new Set();
  if (uniqueUrls.length === 0) return existing;

  if (!adminSupabase) {
    const store = await readNewsStore();
    store
      .filter((item) => uniqueUrls.includes(item.url))
      .forEach((item) => {
        existing.add(item.url);
      });
    return existing;
  }

  for (let index = 0; index < uniqueUrls.length; index += 100) {
    const chunk = uniqueUrls.slice(index, index + 100);
    const { data, error } = await adminSupabase.from('news_articles').select('url').in('url', chunk);
    if (error) {
      if (isMissingTableError(error)) return existing;
      throw error;
    }
    (data || []).forEach((item) => existing.add(item.url));
  }

  return existing;
}

async function translateNewsItem(item) {
  const translated = {
    ...item,
    title_ko: item.title_ko || (await translateToKorean(item.title_original)),
    summary_ko: item.summary_ko || (await translateToKorean(item.summary_original)),
    content_ko: item.content_ko || (await translateLongTextToKorean(item.content_original || item.summary_original)),
    crawled_at: new Date().toISOString(),
  };

  return {
    ...translated,
    keywords: extractKeywords(translated),
  };
}

async function crawlRareDiseaseNews() {
  const errors = [];
  const sourceResults = [];
  const seenUrls = new Set();
  let insertedOrUpdated = 0;
  let storage = 'none';

  for (const source of sources) {
    try {
      const items = await collectSource(source);
      sourceResults.push({ source: source.id, count: items.length });
      const existingUrls = await getExistingNewsUrls(items.map((item) => item.url));
      const rows = [];

      for (const item of items) {
        if (seenUrls.has(item.url)) continue;
        seenUrls.add(item.url);
        if (existingUrls.has(item.url)) continue;

        rows.push(await translateNewsItem(item));
      }

      if (rows.length > 0) {
        storage = await persistNewsRows(rows);
        insertedOrUpdated += rows.length;
      }
    } catch (error) {
      errors.push({ source: source.id, message: formatError(error) });
      sourceResults.push({ source: source.id, count: 0 });
    }
  }

  return { inserted_or_updated: insertedOrUpdated, storage, source_results: sourceResults, errors };
}

async function backfillClinicalTrialNews() {
  const clinicalSources = sources.filter((source) => source.type === 'clinicaltrials');
  const errors = [];
  const sourceResults = [];
  const seenUrls = new Set();
  const candidates = [];
  let storage = adminSupabase ? 'supabase' : 'file';

  for (const source of clinicalSources) {
    try {
      const items = await parseClinicalTrialsSource(source, {
        pageSize: clinicalTrialBackfillPageSize,
        maxPages: clinicalTrialBackfillMaxPages,
        query: {
          'filter.advanced': getClinicalTrialBackfillFilter(),
          sort: 'StudyFirstPostDate:asc',
        },
      });
      const uniqueItems = [];
      for (const item of items) {
        if (seenUrls.has(item.url)) continue;
        seenUrls.add(item.url);
        uniqueItems.push(item);
      }
      sourceResults.push({ source: source.id, scanned: items.length, unique: uniqueItems.length });
      candidates.push(...uniqueItems);
    } catch (error) {
      errors.push({ source: source.id, message: formatError(error) });
      sourceResults.push({ source: source.id, scanned: 0, unique: 0 });
    }
  }

  const existingUrls = await getExistingNewsUrls(candidates.map((item) => item.url));
  const missingItems = candidates.filter((item) => !existingUrls.has(item.url));
  const newItems = missingItems.slice(0, clinicalTrialBackfillMaxRows);
  const rows = [];

  for (const item of newItems) {
    rows.push(await translateNewsItem(item));
  }

  if (rows.length > 0) {
    storage = await persistNewsRows(rows);
  }

  return {
    inserted: rows.length,
    skipped_existing: candidates.length - missingItems.length,
    deferred_by_row_limit: missingItems.length - newItems.length,
    scanned: candidates.length,
    years: clinicalTrialBackfillYears,
    storage,
    source_results: sourceResults,
    errors,
  };
}

async function hydrateNewsArticle(item) {
  const enriched = await enrichItem(item);
  const contentOriginal = normalizeArticleBody(enriched.content_original || enriched.summary_original || '');
  const nextItem = withCountryMetadata({
    ...enriched,
    title_ko: enriched.title_ko || (await translateToKorean(enriched.title_original)),
    summary_ko: enriched.summary_ko || (await translateToKorean(enriched.summary_original)),
    content_ko: await translateLongTextToKorean(contentOriginal),
    crawled_at: new Date().toISOString(),
  });

  return {
    ...nextItem,
    content_ko: nextItem.content_ko || item.content_ko || item.summary_ko,
    keywords: extractKeywords(nextItem),
    news_category: classifyNewsCategory(nextItem),
  };
}

async function backfillNewsDetails() {
  let candidates = [];

  if (adminSupabase) {
    const { data, error } = await adminSupabase
      .from('news_articles')
      .select('id, source_id, source_name, url, title_original, title_ko, summary_original, summary_ko, content_original, content_ko, keywords, published_at, crawled_at')
      .order('crawled_at', { ascending: false })
      .limit(newsDetailBackfillLimit * 3);

    if (error) throw error;
    candidates = (data || []).filter(
      (item) => !item.content_ko || normalizeArticleBody(item.content_original || '').length < minCachedArticleContentLength,
    );
  } else {
    const fileItems = await readStoredNews();
    candidates = fileItems.filter(
      (item) => !item.content_ko || normalizeArticleBody(item.content_original || '').length < minCachedArticleContentLength,
    );
  }

  const rows = [];
  const errors = [];
  for (const item of candidates.slice(0, newsDetailBackfillLimit)) {
    try {
      rows.push(await hydrateNewsArticle(item));
    } catch (error) {
      errors.push({ url: item.url, message: formatError(error) });
    }
  }

  const storage = rows.length > 0 ? await persistNewsRows(rows) : adminSupabase ? 'supabase' : 'file';
  return { updated: rows.length, scanned: candidates.length, storage, errors };
}

app.get('/api/health', (_request, response) => {
  response.json({ ok: true });
});

async function checkOAuthProvider(provider) {
  if (!supabaseUrl || !supabasePublishableKey) {
    return { enabled: false, reason: 'Supabase URL 또는 publishable key가 없습니다.' };
  }

  const authorizeUrl = new URL('/auth/v1/authorize', supabaseUrl);
  authorizeUrl.searchParams.set('provider', provider);
  authorizeUrl.searchParams.set('redirect_to', 'https://rered-production.up.railway.app/');

  try {
    const authResponse = await fetch(authorizeUrl, {
      headers: {
        apikey: supabasePublishableKey,
      },
      redirect: 'manual',
      signal: AbortSignal.timeout(8000),
    });

    if (authResponse.status >= 300 && authResponse.status < 400) {
      return { enabled: true };
    }

    let reason = `${authResponse.status} ${authResponse.statusText}`;
    try {
      const payload = await authResponse.json();
      reason = payload.msg || payload.error_description || payload.error || reason;
    } catch {
      // Keep the status text when the response is not JSON.
    }

    return { enabled: false, reason };
  } catch (error) {
    return { enabled: false, reason: formatError(error) };
  }
}

app.get('/api/auth-providers', async (_request, response) => {
  const [google, kakao] = await Promise.all([checkOAuthProvider('google'), checkOAuthProvider('kakao')]);
  response.json({ google, kakao });
});

app.get('/api/schedules', async (request, response) => {
  const user = await requireUser(request, response);
  if (!user) return;

  const store = await readScheduleStore();
  const ownEntries = store.entries.filter((entry) => entry.user_id === user.id);
  const receivedEntryIds = new Set(
    store.shares.filter((share) => share.shared_with === user.id).map((share) => share.entry_id),
  );
  const sharedEntries = store.entries.filter((entry) => receivedEntryIds.has(entry.id) && entry.user_id !== user.id);
  const ownEntryIds = new Set(ownEntries.map((entry) => entry.id));
  const shares = store.shares.filter((share) => ownEntryIds.has(share.entry_id));
  const profiles = await getProfilesById([
    ...sharedEntries.map((entry) => entry.user_id),
    ...shares.map((share) => share.shared_with),
  ]);

  response.json({
    ownEntries,
    sharedEntries: sharedEntries.map((entry) => ({
      ...entry,
      ownerProfile: profiles.get(entry.user_id) ?? null,
    })),
    shares: shares.map((share) => ({
      ...share,
      profile: profiles.get(share.shared_with) ?? null,
    })),
  });
});

app.post('/api/schedules', async (request, response) => {
  const user = await requireUser(request, response);
  if (!user) return;

  const { id, date_key: dateKey, text = '', images = [] } = request.body ?? {};
  if (!dateKey || !/^\d{4}-\d{2}-\d{2}$/.test(dateKey)) {
    response.status(400).json({ error: 'date_key is required.' });
    return;
  }

  const store = await readScheduleStore();
  const now = new Date().toISOString();
  const existingIndex = store.entries.findIndex((entry) => entry.user_id === user.id && entry.date_key === dateKey);
  const nextText = String(text);
  const nextImages = Array.isArray(images) ? images.filter((image) => typeof image === 'string') : [];

  if (!nextText.trim() && nextImages.length === 0) {
    if (existingIndex >= 0) {
      const [removed] = store.entries.splice(existingIndex, 1);
      store.shares = store.shares.filter((share) => share.entry_id !== removed.id);
      await writeScheduleStore(store);
    }
    response.json({ entry: null });
    return;
  }

  const entry = {
    id: existingIndex >= 0 ? store.entries[existingIndex].id : id || randomUUID(),
    user_id: user.id,
    date_key: dateKey,
    text: nextText,
    images: nextImages,
    created_at: existingIndex >= 0 ? store.entries[existingIndex].created_at : now,
    updated_at: now,
  };

  if (existingIndex >= 0) {
    store.entries[existingIndex] = entry;
  } else {
    store.entries.push(entry);
  }

  await writeScheduleStore(store);
  response.json({ entry });
});

app.post('/api/schedules/:entryId/share', async (request, response) => {
  const user = await requireUser(request, response);
  if (!user) return;

  const { shared_with: sharedWith } = request.body ?? {};
  const store = await readScheduleStore();
  const entry = store.entries.find((item) => item.id === request.params.entryId && item.user_id === user.id);
  if (!entry) {
    response.status(404).json({ error: 'Schedule entry not found.' });
    return;
  }
  if (!sharedWith || sharedWith === user.id) {
    response.status(400).json({ error: 'shared_with is invalid.' });
    return;
  }
  if (store.shares.some((share) => share.entry_id === entry.id && share.shared_with === sharedWith)) {
    response.status(409).json({ error: 'Already shared.' });
    return;
  }

  const share = {
    id: randomUUID(),
    entry_id: entry.id,
    owner_id: user.id,
    shared_with: sharedWith,
    created_at: new Date().toISOString(),
  };
  store.shares.push(share);
  await writeScheduleStore(store);
  response.json({ share });
});

app.delete('/api/schedule-shares/:shareId', async (request, response) => {
  const user = await requireUser(request, response);
  if (!user) return;

  const store = await readScheduleStore();
  const nextShares = store.shares.filter((share) => !(share.id === request.params.shareId && share.owner_id === user.id));
  if (nextShares.length === store.shares.length) {
    response.status(404).json({ error: 'Share not found.' });
    return;
  }
  store.shares = nextShares;
  await writeScheduleStore(store);
  response.json({ ok: true });
});

app.get('/api/news', async (_request, response) => {
  const limit = Math.min(Math.max(100, Number(_request.query.limit || newsListLimit)), 10000);
  if (adminSupabase) {
    const columns =
      'id, source_id, source_name, country_name, country_code, country_flag_code, news_category, url, title_original, title_ko, summary_ko, content_ko, keywords, published_at, crawled_at';
    let { data, error } = await adminSupabase
      .from('news_articles')
      .select(columns)
      .order('published_at', { ascending: false, nullsFirst: false })
      .order('crawled_at', { ascending: false })
      .limit(limit);

    if (
      error &&
      (formatError(error).toLowerCase().includes('country_') ||
        formatError(error).toLowerCase().includes('news_category'))
    ) {
      const fallback = await adminSupabase
        .from('news_articles')
        .select('id, source_id, source_name, url, title_original, title_ko, summary_ko, content_ko, keywords, published_at, crawled_at')
        .order('published_at', { ascending: false, nullsFirst: false })
        .order('crawled_at', { ascending: false })
        .limit(limit);
      data = fallback.data;
      error = fallback.error;
    }

    if (!error) {
      response.json({
        storage: 'supabase',
        items: (data || []).map((item) => {
          const itemWithCountry = withCountryMetadata(item);
          return { ...itemWithCountry, news_category: classifyNewsCategory(itemWithCountry) };
        }),
      });
      return;
    }

    if (
      !isMissingTableError(error) &&
      !formatError(error).toLowerCase().includes('keywords') &&
      !formatError(error).toLowerCase().includes('content_ko')
    ) {
      response.status(500).json({ error: formatError(error) });
      return;
    }
  }

  const items = await readStoredNews();
  response.json({
    storage: 'file',
    items: items.slice(0, limit).map((item) => {
      const itemWithCountry = withCountryMetadata(item);
      return { ...itemWithCountry, news_category: classifyNewsCategory(itemWithCountry) };
    }),
  });
});

app.get('/api/news-detail', async (request, response) => {
  const url = String(request.query.url || '');
  if (!url) {
    response.status(400).json({ error: 'url is required' });
    return;
  }

  let item = null;
  if (adminSupabase) {
    let { data, error } = await adminSupabase
      .from('news_articles')
      .select('id, source_id, source_name, country_name, country_code, country_flag_code, news_category, url, title_original, title_ko, summary_original, summary_ko, content_original, content_ko, keywords, published_at, crawled_at')
      .eq('url', url)
      .maybeSingle();
    if (
      error &&
      (formatError(error).toLowerCase().includes('country_') ||
        formatError(error).toLowerCase().includes('news_category'))
    ) {
      const fallback = await adminSupabase
        .from('news_articles')
        .select('id, source_id, source_name, url, title_original, title_ko, summary_original, summary_ko, content_original, content_ko, keywords, published_at, crawled_at')
        .eq('url', url)
        .maybeSingle();
      data = fallback.data;
      error = fallback.error;
    }
    if (error && !formatError(error).toLowerCase().includes('content_ko')) {
      response.status(500).json({ error: formatError(error) });
      return;
    }
    if (data) {
      const itemWithCountry = withCountryMetadata(data);
      item = { ...itemWithCountry, news_category: classifyNewsCategory(itemWithCountry) };
    }
  }

  if (!item) {
    const fileItems = await readStoredNews();
    const fileItem = fileItems.find((row) => row.url === url) || null;
    if (fileItem) {
      const itemWithCountry = withCountryMetadata(fileItem);
      item = { ...itemWithCountry, news_category: classifyNewsCategory(itemWithCountry) };
    }
  }

  if (!item) {
    response.status(404).json({ error: 'article not found' });
    return;
  }

  const hasShortOriginal = normalizeArticleBody(item.content_original || '').length < minCachedArticleContentLength;

  if (hasShortOriginal || !item.content_ko) {
    try {
      const details = await fetchArticleDetails(item.url, item.title_original);
      const existingContent = normalizeArticleBody(item.content_original || '');
      const fetchedContent = normalizeArticleBody(details.content || '');
      const contentOriginal =
        fetchedContent.length > existingContent.length
          ? fetchedContent
          : existingContent || normalizeArticleBody(item.summary_original || details.summary || '');
      const contentKo = await translateLongTextToKorean(contentOriginal);
      item = {
        ...item,
        title_original: details.title || item.title_original,
        title_ko: details.title ? await translateToKorean(details.title) : item.title_ko,
        summary_original: item.summary_original || details.summary,
        summary_ko: item.summary_ko || (details.summary ? await translateToKorean(details.summary) : ''),
        content_original: contentOriginal,
        content_ko: contentKo || item.content_ko || item.summary_ko,
        published_at: item.published_at || details.publishedAt,
        crawled_at: new Date().toISOString(),
        news_category: classifyNewsCategory({ ...item, ...details }),
      };

      if (adminSupabase) {
        await adminSupabase
          .from('news_articles')
          .update({
            title_original: item.title_original,
            title_ko: item.title_ko,
            summary_original: item.summary_original,
            summary_ko: item.summary_ko,
            content_original: item.content_original,
            content_ko: item.content_ko,
            country_name: item.country_name,
            country_code: item.country_code,
            country_flag_code: item.country_flag_code,
            news_category: item.news_category,
            published_at: item.published_at,
            crawled_at: item.crawled_at,
          })
          .eq('url', item.url);
      } else {
        await upsertFileNews([item]);
      }
    } catch (error) {
      console.error('[news-detail]', formatError(error));
    }
  }

  response.json({ item });
});

app.get('/api/krdis-diseases', async (request, response) => {
  const query = normalizeText(String(request.query.q || ''));
  if (query.length < 2) {
    response.json({ source: 'KRDIS', items: [] });
    return;
  }

  try {
    const items = await searchKrdisDiseases(query);
    response.json({ source: 'KRDIS', items });
  } catch (error) {
    response.status(500).json({ error: formatError(error) });
  }
});

app.get('/api/krdis-disease-detail', async (request, response) => {
  const url = String(request.query.url || '');
  if (!url) {
    response.status(400).json({ error: 'url is required' });
    return;
  }

  try {
    const item = await getKrdisDiseaseDetail(url);
    response.json({ item });
  } catch (error) {
    response.status(500).json({ error: formatError(error) });
  }
});

app.post('/api/crawl-news', async (request, response) => {
  if (!crawlSecret || request.get('x-crawl-secret') !== crawlSecret) {
    response.status(401).json({ error: 'Unauthorized' });
    return;
  }

  try {
    const result = await crawlRareDiseaseNews();
    response.json(result);
  } catch (error) {
    response.status(500).json({ error: formatError(error) });
  }
});

app.get('/api/news-sources', (_request, response) => {
  response.json({
    count: sources.length,
    sources: sources.map(({ id, name, type, url }) => ({ id, name, type, url, country: sourceCountries[id] || null })),
  });
});

app.post('/api/backfill-news-details', async (request, response) => {
  if (!crawlSecret || request.get('x-crawl-secret') !== crawlSecret) {
    response.status(401).json({ error: 'Unauthorized' });
    return;
  }

  try {
    const result = await backfillNewsDetails();
    response.json(result);
  } catch (error) {
    response.status(500).json({ error: formatError(error) });
  }
});

app.post('/api/backfill-clinical-trials', async (request, response) => {
  if (!crawlSecret || request.get('x-crawl-secret') !== crawlSecret) {
    response.status(401).json({ error: 'Unauthorized' });
    return;
  }

  try {
    const result = await backfillClinicalTrialNews();
    response.json(result);
  } catch (error) {
    response.status(500).json({ error: formatError(error) });
  }
});

app.post('/api/sync-diseases', async (request, response) => {
  if (!crawlSecret || request.get('x-crawl-secret') !== crawlSecret) {
    response.status(401).json({ error: 'Unauthorized' });
    return;
  }

  try {
    const result = await syncDiseaseCategories();
    response.json(result);
  } catch (error) {
    response.status(500).json({ error: formatError(error) });
  }
});

if (process.argv.includes('--crawl-news-once')) {
  crawlRareDiseaseNews()
    .then((result) => {
      console.log(JSON.stringify(result, null, 2));
      process.exit(0);
    })
    .catch((error) => {
      console.error(formatError(error));
      process.exit(1);
    });
} else if (process.argv.includes('--backfill-news-details')) {
  backfillNewsDetails()
    .then((result) => {
      console.log(JSON.stringify(result, null, 2));
      process.exit(0);
    })
    .catch((error) => {
      console.error(formatError(error));
      process.exit(1);
    });
} else if (process.argv.includes('--backfill-clinical-trials')) {
  backfillClinicalTrialNews()
    .then((result) => {
      console.log(JSON.stringify(result, null, 2));
      process.exit(0);
    })
    .catch((error) => {
      console.error(formatError(error));
      process.exit(1);
    });
} else {

cron.schedule(
  '0 */2 * * *',
  () => {
    crawlRareDiseaseNews().catch((error) => {
      console.error('[crawl-news]', error);
    });
  },
  { timezone: 'Asia/Seoul' },
);

cron.schedule(
  '0 0 * * *',
  () => {
    syncDiseaseCategories().catch((error) => {
      console.error('[sync-diseases]', error);
    });
  },
  { timezone: 'Asia/Seoul' },
);

setTimeout(() => {
  crawlRareDiseaseNews().catch((error) => {
    console.error('[startup-crawl-news]', error);
  });
}, 5000);

app.use(express.static(path.join(__dirname, 'dist')));
app.get(/.*/, (_request, response) => {
  response.sendFile(path.join(__dirname, 'dist', 'index.html'));
});

app.listen(port, () => {
  console.log(`RareCare Korea server listening on ${port}`);
});
}
