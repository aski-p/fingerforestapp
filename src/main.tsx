import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import type { User } from '@supabase/supabase-js';
import {
  AlertCircle,
  Bell,
  BookOpen,
  Camera,
  CalendarDays,
  ChevronRight,
  FileText,
  HeartHandshake,
  Home,
  ImagePlus,
  Lock,
  LogIn,
  LogOut,
  MessageCircle,
  Newspaper,
  Save,
  Search,
  Settings,
  Share2,
  ShieldCheck,
  Trash2,
  UserPlus,
  UserRound,
  Users,
  X,
} from 'lucide-react';
import { isSupabaseConfigured, supabase } from './lib/supabase';
import './styles.css';

type Tab = 'home' | 'disease-search' | 'news' | 'board' | 'schedule' | 'signup' | 'profile';
type ScheduleEntry = {
  id?: string;
  userId?: string;
  text: string;
  images: string[];
  updatedAt?: string;
};
type SharedScheduleEntry = ScheduleEntry & {
  id: string;
  dateKey: string;
  ownerId: string;
  ownerNickname: string;
  ownerName: string | null;
};
type ScheduleShare = {
  id: string;
  entry_id: string;
  shared_with: string;
  created_at: string;
  profile?: MemberProfile;
};
type MemberProfile = {
  id: string;
  nickname: string;
  full_name: string | null;
};
type ScheduleApiEntry = {
  id: string;
  user_id: string;
  date_key: string;
  text: string | null;
  images: string[] | null;
  updated_at: string;
  ownerProfile?: MemberProfile | null;
};
type BoardPost = {
  id: string;
  category_id: string;
  title: string;
  body: string;
  created_at: string;
};
type BoardCategory = {
  id: string;
  orpha_code: string | null;
  name_en: string;
  name_ko: string | null;
  gene_symbols: string[] | null;
  aliases: string[] | null;
};
type BoardComment = {
  id: string;
  post_id: string;
  body: string;
  created_at: string;
};
type NoticePost = {
  id: string;
  title: string;
  body: string;
  pinned: boolean;
  created_at: string;
};
type NewsArticle = {
  id: string;
  source_id: string | null;
  source_name: string;
  country_name: string | null;
  country_code: string | null;
  country_flag_code: string | null;
  news_category: string | null;
  url: string;
  title_original: string;
  title_ko: string;
  summary_ko: string | null;
  content_ko: string | null;
  keywords: string[] | null;
  published_at: string | null;
  crawled_at: string | null;
};
type OAuthProviderStatus = {
  google: { enabled: boolean; reason?: string };
  kakao: { enabled: boolean; reason?: string };
};
type KrdisDiseaseResult = {
  id: string;
  name_ko: string;
  name_en: string | null;
  category: string | null;
  kcd_code: string | null;
  gene_symbols: string[];
  aliases?: string[];
  url: string;
  source: string;
};
type KrdisDiseaseDetail = {
  name_ko: string | null;
  name_en: string | null;
  kid_code: string | null;
  gene_symbols: string[];
  sections: Array<{
    title_ko: string;
    title_en: string | null;
    body: string;
  }>;
  source: string;
  source_url: string;
};

const diseaseCategorySearchMetadata: Record<
  string,
  Pick<BoardCategory, 'gene_symbols' | 'aliases'> & { name_ko?: string }
> = {
  '457279': {
    gene_symbols: ['PPP2R5D'],
    aliases: [
      'PPP2R5D-related neurodevelopmental disorder',
      'PPP2R5D-related intellectual disability',
      'Jordan syndrome',
      "Jordan's syndrome",
      'Houge-Janssens syndrome 1',
    ],
    name_ko: '지적장애-대두증-근긴장저하-행동이상 증후군',
  },
};

function withDiseaseSearchMetadata(category: Omit<BoardCategory, 'gene_symbols' | 'aliases'>): BoardCategory {
  const metadata = category.orpha_code ? diseaseCategorySearchMetadata[category.orpha_code] : null;

  return {
    ...category,
    name_ko: category.name_ko ?? metadata?.name_ko ?? null,
    gene_symbols: metadata?.gene_symbols ?? [],
    aliases: metadata?.aliases ?? [],
  };
}
type ProfileFormState = {
  full_name: string;
  phone: string;
  birth_date: string;
  region: string;
  relationship: string;
  topic: string;
  bio: string;
  email_visibility: string;
  notification_opt_in: boolean;
  keep_health_private: boolean;
};

const tabs: Array<{ id: Tab; label: string; icon: React.ElementType }> = [
  { id: 'home', label: '희귀질환 정보', icon: Home },
  { id: 'disease-search', label: '희귀병 검색', icon: Search },
  { id: 'news', label: 'News', icon: Newspaper },
  { id: 'board', label: '게시판', icon: MessageCircle },
  { id: 'schedule', label: '나의 일정', icon: CalendarDays },
  { id: 'signup', label: '회원가입', icon: UserRound },
  { id: 'profile', label: '회원정보', icon: ShieldCheck },
];

const keyFacts = [
  '국내 희귀질환 환자와 가족이 질환 정보, 제도, 진료 경험을 함께 정리하는 공간입니다.',
  '질환마다 증상과 치료 경로가 다르기 때문에 검증된 자료와 실제 생활 경험을 구분해서 다룹니다.',
  '진단 이후에는 전문 진료, 재활, 복지 제도, 심리적 지지까지 이어지는 장기적인 지원이 중요합니다.',
];

const sources = [
  {
    label: '질병관리청 희귀질환 헬프라인',
    description: '국내 희귀질환 정보, 산정특례, 의료비 지원, 전문기관 정보를 확인할 수 있는 공공 자료',
    href: 'https://helpline.kdca.go.kr/',
  },
  {
    label: 'Orphanet',
    description: '희귀질환별 개요, 유전 정보, 전문 자료를 제공하는 국제 희귀질환 데이터베이스',
    href: 'https://www.orpha.net/',
  },
];

const weekdays = ['일', '월', '화', '수', '목', '금', '토'];
const newsKeywordStorageKey = 'rarecare-news-keywords';
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
  'orphan drug',
  '임상시험',
  '임상 시험',
  '치료제 개발',
  '희귀의약품',
];
const newsCategoryOptions = [
  { id: 'all', label: '전체' },
  { id: 'general', label: '일반 뉴스' },
  { id: 'clinical_trial', label: '임상시험·치료제 개발' },
];
type NewsCountry = {
  id: string;
  name: string;
  code: string;
  emoji: string;
  flagCode?: string;
};
const defaultNewsCountry: NewsCountry = { id: 'international', name: '국제', code: 'INT', emoji: '🌐' };
const newsCountries: Record<string, NewsCountry> = {
  international: defaultNewsCountry,
  korea: { id: 'korea', name: '대한민국', code: '82', emoji: '🇰🇷', flagCode: 'kr' },
  usa: { id: 'usa', name: '미국', code: '1', emoji: '🇺🇸', flagCode: 'us' },
  europe: { id: 'europe', name: '유럽', code: 'EU', emoji: '🇪🇺', flagCode: 'eu' },
  australia: { id: 'australia', name: '호주', code: '61', emoji: '🇦🇺', flagCode: 'au' },
  canada: { id: 'canada', name: '캐나다', code: '1', emoji: '🇨🇦', flagCode: 'ca' },
  uk: { id: 'uk', name: '영국', code: '44', emoji: '🇬🇧', flagCode: 'gb' },
  newzealand: { id: 'newzealand', name: '뉴질랜드', code: '64', emoji: '🇳🇿', flagCode: 'nz' },
  southafrica: { id: 'southafrica', name: '남아공', code: '27', emoji: '🇿🇦', flagCode: 'za' },
  japan: { id: 'japan', name: '일본', code: '81', emoji: '🇯🇵', flagCode: 'jp' },
  spain: { id: 'spain', name: '스페인', code: '34', emoji: '🇪🇸', flagCode: 'es' },
  france: { id: 'france', name: '프랑스', code: '33', emoji: '🇫🇷', flagCode: 'fr' },
  italy: { id: 'italy', name: '이탈리아', code: '39', emoji: '🇮🇹', flagCode: 'it' },
  bulgaria: { id: 'bulgaria', name: '불가리아', code: '359', emoji: '🇧🇬', flagCode: 'bg' },
};
const countryOptionOrder = [
  'korea',
  'usa',
  'europe',
  'japan',
  'uk',
  'canada',
  'australia',
  'newzealand',
  'southafrica',
  'spain',
  'france',
  'italy',
  'bulgaria',
  'international',
];
const newsSourceCountryMap: Record<string, string> = {
  'nord-news': 'usa',
  'global-genes': 'usa',
  'rare-disease-advisor': 'usa',
  'rare-x': 'usa',
  'everylife-foundation': 'usa',
  'patient-worthy': 'usa',
  'ncats-news': 'usa',
  'nih-reporter-rare-diseases': 'usa',
  'fda-rare-diseases': 'usa',
  'fda-orphan-products': 'usa',
  'eurordis-news': 'europe',
  'rare-diseases-international': 'international',
  'rare-disease-day': 'international',
  irdirc: 'international',
  'rare-revolution': 'uk',
  'rare-voices-australia': 'australia',
  'cord-canada': 'canada',
  'genetic-alliance-uk': 'uk',
  'beacon-uk': 'uk',
  'unique-rare-chromosome': 'uk',
  'rare-disorders-nz': 'newzealand',
  'rare-diseases-south-africa': 'southafrica',
  'raddar-japan': 'japan',
  'shionogi-news': 'japan',
  'shionogi-clinical-trials': 'japan',
  'clinicaltrials-gov-rare-disease': 'international',
  'clinicaltrials-gov-orphan-drug': 'international',
  'google-news-rare-clinical-trials': 'international',
  'google-news-ppp2r5d': 'international',
  'known-ppp2r5d-trials': 'japan',
  'feder-spain': 'spain',
  'alliance-maladies-rares-france': 'france',
  'uniamo-italy': 'italy',
  'raredis-bulgaria': 'bulgaria',
  'ema-whats-new': 'europe',
  'ema-rss-news': 'europe',
  'orphanet-news': 'europe',
  'orphanet-journal': 'europe',
  'ern-rnd': 'europe',
  'snuh-rare-disease-center': 'korea',
  'snuh-child-lectures': 'korea',
  'snuh-child-news': 'korea',
  'kdca-search': 'korea',
  'known-korea-rare-disease': 'korea',
};
function getNewsCountry(item: Pick<NewsArticle, 'source_id' | 'country_name' | 'country_code' | 'country_flag_code'>): NewsCountry {
  const countryId = item.source_id ? newsSourceCountryMap[item.source_id] : null;
  const fallback = countryId ? newsCountries[countryId] || defaultNewsCountry : defaultNewsCountry;
  return {
    ...fallback,
    name: item.country_name || fallback.name,
    code: item.country_code || fallback.code,
    flagCode: item.country_flag_code || fallback.flagCode,
  };
}

function getNewsCategory(item: Pick<NewsArticle, 'source_id' | 'news_category' | 'url' | 'title_original' | 'title_ko' | 'summary_ko' | 'content_ko' | 'keywords'>) {
  if (item.news_category) return item.news_category;
  if (item.source_id === 'known-ppp2r5d-trials' || item.source_id === 'shionogi-clinical-trials') return 'clinical_trial';

  const haystack = [
    item.url,
    item.title_original,
    item.title_ko,
    item.summary_ko,
    item.content_ko,
    ...(item.keywords ?? []),
  ]
    .join(' ')
    .toLowerCase();

  return clinicalTrialTerms.some((term) => haystack.includes(term.toLowerCase())) ? 'clinical_trial' : 'general';
}

function getNewsCategoryLabel(category: string) {
  return newsCategoryOptions.find((option) => option.id === category)?.label ?? '일반 뉴스';
}

function normalizeDisplayText(value = '') {
  return value.replace(/\s+/g, ' ').trim();
}

type ClinicalTimelineItem = {
  id: string;
  yearLabel: string;
  phaseLabel: string;
  treatmentLabel: string;
  statusLabel: string;
  title: string;
  source: string;
  article: NewsArticle;
  sortValue: number;
};
type ClinicalDrugTimelineGroup = {
  drugName: string;
  items: ClinicalTimelineItem[];
  summary: string;
  effectNote: string;
};

function extractYearFromDate(value: string | null) {
  if (!value) return null;
  const year = new Date(value).getFullYear();
  return Number.isNaN(year) ? null : year;
}

function extractYearAfterLabel(text: string, label: string) {
  const match = text.match(new RegExp(`${label}:?\\s*(\\d{4})`, 'i'));
  return match ? Number(match[1]) : null;
}

function extractClinicalPhase(text: string) {
  const phaseMatch = text.match(/phase\s*([123])|phase([123])|PHASE([123])/i);
  if (phaseMatch) return `${phaseMatch[1] || phaseMatch[2] || phaseMatch[3]}상 임상`;
  if (/open-label|extension|연장/i.test(text)) return '연장 연구';
  if (/recruiting|enrolling|모집/i.test(text)) return '모집/진행';
  return '임상 자료';
}

function extractTreatmentLabel(text: string, title: string) {
  const labeled = text.match(/Investigational treatment:\s*([^\n]+)/i);
  if (labeled?.[1]) return normalizeDisplayText(labeled[1].split(',')[0]);

  const known = ['zatolmilast', 'S-606001', 'hydrocortisone', 'cabozantinib', 'nivolumab', 'ipilimumab'];
  const lower = `${title} ${text}`.toLowerCase();
  const found = known.find((name) => lower.includes(name.toLowerCase()));
  if (found) return found;

  return '치료제/중재 확인';
}

function extractStatusLabel(text: string) {
  const labeled = text.match(/Status:\s*([^\n]+)/i);
  if (labeled?.[1]) return labeled[1].replace(/_/g, ' ').trim();
  if (/recruiting|모집/i.test(text)) return 'RECRUITING';
  if (/completed|완료/i.test(text)) return 'COMPLETED';
  if (/active/i.test(text)) return 'ACTIVE';
  return '상세 확인';
}

function extractClinicalEffectNote(item: NewsArticle) {
  const body = [item.summary_ko, item.content_ko, item.title_ko, item.title_original].filter(Boolean).join('\n');
  const sentences = body
    .split(/(?<=[.!?。])\s+|\n{1,}/)
    .map((line) => normalizeDisplayText(line))
    .filter(Boolean);
  const effectSentences = sentences.filter((sentence) =>
    /효과|개선|평가|결과|안전|인지|내약|유효|endpoint|efficacy|safety|tolerability|outcome|improv/i.test(sentence),
  );
  return (effectSentences[0] || sentences[0] || '효과와 안전성 정보는 원문 상세에서 확인할 수 있습니다.').slice(0, 220);
}

function buildClinicalTimelineGroups(items: NewsArticle[]): ClinicalDrugTimelineGroup[] {
  const timelineItems = items
    .filter((item) => getNewsCategory(item) === 'clinical_trial')
    .map((item) => {
      const text = [item.title_original, item.title_ko, item.summary_ko, item.content_ko, ...(item.keywords ?? [])].join('\n');
      const startYear = extractYearAfterLabel(text, 'Start');
      const completionYear = extractYearAfterLabel(text, 'Completion');
      const publishedYear = extractYearFromDate(item.published_at);
      const fallbackYear = publishedYear ?? extractYearFromDate(item.crawled_at) ?? new Date().getFullYear();
      const yearLabel =
        startYear && completionYear && startYear !== completionYear
          ? `${startYear}~${completionYear}`
          : `${startYear ?? completionYear ?? fallbackYear}`;

      return {
        id: item.id,
        yearLabel,
        phaseLabel: extractClinicalPhase(text),
        treatmentLabel: extractTreatmentLabel(text, item.title_original),
        statusLabel: extractStatusLabel(text),
        title: item.title_ko || item.title_original,
        source: item.source_name,
        article: item,
        sortValue: startYear ?? publishedYear ?? completionYear ?? fallbackYear,
      };
    })
    .sort((first, second) => first.sortValue - second.sortValue);

  const groups = new Map<string, ClinicalTimelineItem[]>();
  timelineItems.forEach((item) => {
    const drugName = item.treatmentLabel || '치료제/중재 확인';
    groups.set(drugName, [...(groups.get(drugName) ?? []), item]);
  });

  return Array.from(groups.entries())
    .map(([drugName, groupItems]) => {
      const sortedItems = groupItems.sort((first, second) => first.sortValue - second.sortValue);
      const first = sortedItems[0];
      const last = sortedItems[sortedItems.length - 1];
      const yearRange =
        first.yearLabel === last.yearLabel ? first.yearLabel : `${first.yearLabel.split('~')[0]}~${last.yearLabel.split('~').pop()}`;

      return {
        drugName,
        items: sortedItems.slice(0, 6),
        summary: `${yearRange} · ${sortedItems.map((item) => item.phaseLabel).filter(Boolean).join(' → ')}`,
        effectNote: extractClinicalEffectNote(last.article),
      };
    })
    .sort((first, second) => first.items[0].sortValue - second.items[0].sortValue)
    .slice(0, 6);
}
const defaultProfileForm: ProfileFormState = {
  full_name: '',
  phone: '',
  birth_date: '',
  region: '',
  relationship: 'guardian',
  topic: 'care',
  bio: '',
  email_visibility: 'private',
  notification_opt_in: true,
  keep_health_private: true,
};

function toDateKey(date: Date) {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formatKoreanDate(dateKey: string) {
  const [year, month, day] = dateKey.split('-');
  return `${year}년 ${Number(month)}월 ${Number(day)}일`;
}

function formatDailyRecordSavedMessage(dateKey: string) {
  const [, month, day] = dateKey.split('-');
  return `${Number(month)}월 ${Number(day)}일 아이의 일상이 저장되었습니다.`;
}

function getCalendarDays(monthDate: Date) {
  const year = monthDate.getFullYear();
  const month = monthDate.getMonth();
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const days: Array<{ date: Date; inMonth: boolean; key: string }> = [];

  for (let index = firstDay.getDay(); index > 0; index -= 1) {
    const date = new Date(year, month, 1 - index);
    days.push({ date, inMonth: false, key: toDateKey(date) });
  }

  for (let day = 1; day <= lastDay.getDate(); day += 1) {
    const date = new Date(year, month, day);
    days.push({ date, inMonth: true, key: toDateKey(date) });
  }

  while (days.length % 7 !== 0) {
    const date = new Date(year, month + 1, days.length - firstDay.getDay() - lastDay.getDate() + 1);
    days.push({ date, inMonth: false, key: toDateKey(date) });
  }

  return days;
}

function readImages(files: FileList | null): Promise<string[]> {
  if (!files?.length) return Promise.resolve([]);

  return Promise.all(
    Array.from(files).map(
      (file) =>
        new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result));
          reader.onerror = () => reject(reader.error);
          reader.readAsDataURL(file);
        }),
    ),
  );
}

function normalizeAuthErrorMessage(message: string) {
  if (/Unsupported provider|provider is not enabled/i.test(message)) {
    return 'Supabase에서 Google/Kakao 로그인 제공자가 아직 활성화되지 않았습니다. Authentication Providers에서 Google과 Kakao를 켜고 Client ID/Secret을 등록해야 합니다.';
  }
  if (/redirect|not allowed|not.*authorized/i.test(message)) {
    return '소셜 로그인 Redirect URL이 허용 목록에 없습니다. Supabase Auth URL 설정에 현재 Railway 주소를 추가해야 합니다.';
  }
  return message;
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function keywordMatchesText(keyword: string, text: string) {
  const normalizedKeyword = keyword.trim().toLowerCase();
  if (!normalizedKeyword) return false;

  if (/^[a-z0-9][a-z0-9 -]*$/i.test(normalizedKeyword)) {
    const pattern = new RegExp(`(^|[^a-z0-9])${escapeRegExp(normalizedKeyword)}([^a-z0-9]|$)`, 'i');
    return pattern.test(text);
  }

  return text.toLowerCase().includes(normalizedKeyword);
}

function getScheduleStorageKey(userId: string) {
  return `rarecare-schedule-${userId}`;
}

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('home');
  const [nickname, setNickname] = useState('rare_family');
  const [photoPreview, setPhotoPreview] = useState('');
  const [authMessage, setAuthMessage] = useState('');
  const [oauthProviders, setOauthProviders] = useState<OAuthProviderStatus | null>(null);
  const [profileMessage, setProfileMessage] = useState('');
  const [user, setUser] = useState<User | null>(null);
  const [profileForm, setProfileForm] = useState<ProfileFormState>(defaultProfileForm);

  const activeLabel = useMemo(() => tabs.find((tab) => tab.id === activeTab)?.label ?? '희귀질환 정보', [activeTab]);
  const visibleTabs = useMemo(
    () => tabs.filter((tab) => tab.id !== 'signup' && (user || tab.id !== 'profile')),
    [user],
  );

  function handlePhotoChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setPhotoPreview(URL.createObjectURL(file));
  }

  useEffect(() => {
    if (!supabase) {
      return undefined;
    }

    const client = supabase;
    const params = new URLSearchParams(`${window.location.search}&${window.location.hash.replace(/^#/, '')}`);
    const authError = params.get('error_description') ?? params.get('error');
    if (authError) {
      setAuthMessage(normalizeAuthErrorMessage(decodeURIComponent(authError).replace(/\+/g, ' ')));
    }

    async function initializeSession() {
      const code = params.get('code') || new URLSearchParams(window.location.search).get('code');

      if (code) {
        const { data: exchangeData, error } = await client.auth.exchangeCodeForSession(code);
        if (error) {
          setAuthMessage(normalizeAuthErrorMessage(error.message));
        } else {
          const sessionUser = exchangeData.session?.user ?? null;
          if (sessionUser) {
            setUser(sessionUser);
            void loadUserProfile(sessionUser);
            setAuthMessage('로그인되었습니다. 회원정보를 확인해 주세요.');
            setActiveTab('profile');
          }
          window.history.replaceState({}, document.title, window.location.pathname || '/');
        }
      }

      const { data, error } = await client.auth.getSession();
      if (error) {
        setAuthMessage(normalizeAuthErrorMessage(error.message));
        return;
      }

      const sessionUser = data.session?.user ?? null;
      setUser(sessionUser);
      if (sessionUser) {
        void loadUserProfile(sessionUser);
        setActiveTab('profile');
      }
    }

    initializeSession();

    const {
      data: { subscription },
    } = client.auth.onAuthStateChange((event, session) => {
      const sessionUser = session?.user ?? null;
      setUser(sessionUser);

      if (event === 'SIGNED_IN' && sessionUser) {
        void loadUserProfile(sessionUser);
        setAuthMessage('로그인되었습니다. 회원정보를 확인해 주세요.');
        setActiveTab('profile');
      }

      if (event === 'SIGNED_OUT') {
        setAuthMessage('로그아웃되었습니다.');
        setProfileMessage('');
        setProfileForm(defaultProfileForm);
        setPhotoPreview('');
        setNickname('rare_family');
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!isSupabaseConfigured) return;

    fetch('/api/auth-providers')
      .then((response) => {
        if (!response.ok) throw new Error('소셜 로그인 설정을 확인하지 못했습니다.');
        return response.json();
      })
      .then((status: OAuthProviderStatus) => {
        setOauthProviders(status);
        if (!status.google.enabled && !status.kakao.enabled) {
          setAuthMessage('Supabase에서 Google/Kakao 로그인 제공자가 아직 활성화되지 않았습니다. Provider Client ID/Secret 등록 후 사용할 수 있습니다.');
          return;
        }

      })
      .catch((error) => setAuthMessage(error.message));
  }, []);

  useEffect(() => {
    if (user && activeTab === 'signup') {
      setActiveTab('profile');
    }
    if (!user && activeTab === 'profile') {
      openAuthGuide('login');
    }
  }, [activeTab, user]);

  async function loadUserProfile(currentUser: User) {
    if (!supabase) return;

    const pendingNickname = localStorage.getItem('rarecare-pending-nickname');
    const fallbackNickname =
      pendingNickname ||
      currentUser.user_metadata.preferred_username ||
      currentUser.user_metadata.name ||
      currentUser.email?.split('@')[0] ||
      'rare_member';

    const { data, error } = await supabase.from('profiles').select('*').eq('id', currentUser.id).maybeSingle();

    if (error) {
      setAuthMessage(`프로필을 불러오지 못했습니다: ${error.message}`);
      return;
    }

    if (!data) {
      await saveUserProfile(currentUser, { nickname: fallbackNickname }, false);
      return;
    }

    const nextNickname = data.nickname || fallbackNickname;
    setNickname(nextNickname);
    setPhotoPreview(data.avatar_url || currentUser.user_metadata.avatar_url || currentUser.user_metadata.picture || '');
    setProfileForm({
      full_name: data.full_name ?? currentUser.user_metadata.name ?? '',
      phone: data.phone ?? '',
      birth_date: data.birth_date ?? '',
      region: data.region ?? '',
      relationship: data.relationship ?? 'guardian',
      topic: data.topic ?? 'care',
      bio: data.bio ?? '',
      email_visibility: data.email_visibility ?? 'private',
      notification_opt_in: data.notification_opt_in ?? true,
      keep_health_private: data.keep_health_private ?? true,
    });

    if (pendingNickname && pendingNickname !== data.nickname) {
      await saveUserProfile(currentUser, { nickname: pendingNickname }, false);
    }
    localStorage.removeItem('rarecare-pending-nickname');
  }

  async function saveUserProfile(currentUser = user, overrides: Partial<{ nickname: string }> = {}, showMessage = true) {
    if (!supabase || !currentUser) {
      setAuthMessage('먼저 Google 또는 Kakao 계정으로 로그인해 주세요.');
      return;
    }

    const nextNickname = (overrides.nickname ?? nickname).trim() || 'rare_member';
    const { error } = await supabase.from('profiles').upsert({
      id: currentUser.id,
      nickname: nextNickname,
      full_name: profileForm.full_name || currentUser.user_metadata.name || null,
      phone: profileForm.phone || null,
      birth_date: profileForm.birth_date || null,
      region: profileForm.region || null,
      relationship: profileForm.relationship,
      topic: profileForm.topic,
      bio: profileForm.bio || null,
      avatar_url: photoPreview || currentUser.user_metadata.avatar_url || currentUser.user_metadata.picture || null,
      email_visibility: profileForm.email_visibility,
      notification_opt_in: profileForm.notification_opt_in,
      keep_health_private: profileForm.keep_health_private,
    });

    if (error) {
      setProfileMessage(`저장 실패: ${error.message}`);
      return;
    }

    setNickname(nextNickname);
    if (showMessage) {
      setProfileMessage('회원정보가 저장되었습니다.');
      setAuthMessage('가입 정보가 저장되었습니다.');
    }
  }

  async function handleOAuthSignIn(provider: 'google' | 'kakao') {
    if (!supabase) {
      setAuthMessage('Supabase 환경변수가 설정되지 않았습니다.');
      return;
    }

    const providerStatus = oauthProviders?.[provider];
    if (providerStatus && !providerStatus.enabled) {
      setAuthMessage(
        `${provider === 'google' ? 'Google' : 'Kakao'} 로그인이 Supabase에서 아직 활성화되지 않았습니다. Client ID/Secret을 등록하고 Provider를 켜야 합니다.`,
      );
      return;
    }

    localStorage.setItem('rarecare-pending-nickname', nickname.trim() || 'rare_member');
    setAuthMessage('로그인 페이지로 이동 중입니다.');
    const redirectTo = new URL(window.location.pathname || '/', window.location.origin).toString();
    const { error } = await supabase.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo,
        scopes: provider === 'kakao' ? 'profile_nickname profile_image account_email' : undefined,
        queryParams: provider === 'google' ? { prompt: 'select_account' } : undefined,
      },
    });

    if (error) {
      setAuthMessage(normalizeAuthErrorMessage(error.message));
    }
  }

  async function handleSignOut() {
    if (!supabase) return;
    await supabase.auth.signOut();
    setUser(null);
    setActiveTab('home');
  }

  function openAuthGuide(intent: 'login' | 'signup') {
    setAuthMessage(
      intent === 'login'
        ? 'Google 또는 Kakao 버튼을 눌러 로그인해 주세요. 처음 방문한 계정은 로그인 후 회원정보를 저장하면 가입이 완료됩니다.'
        : 'Google 또는 Kakao 계정으로 먼저 인증한 뒤 닉네임과 공개 범위를 저장하면 회원가입이 완료됩니다.',
    );
    setActiveTab('signup');
    window.setTimeout(() => document.getElementById('account-login')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
  }

  return (
    <main>
      <header className="app-header">
        <div className="header-top">
          <a className="brand" href="#home" onClick={() => setActiveTab('home')}>
            <span>RareCare Korea</span>
            <small>국내 희귀질환 커뮤니티</small>
          </a>
          <div className="header-actions">
            {user ? (
              <>
                <div className="header-profile">
                  {photoPreview ? (
                    <img alt={`${nickname} 프로필`} src={photoPreview} />
                  ) : (
                    <span className="header-profile__fallback">{nickname.slice(0, 1).toUpperCase()}</span>
                  )}
                  <strong>{nickname}</strong>
                  <button
                    aria-label="개인정보 수정"
                    onClick={() => setActiveTab('profile')}
                    title="개인정보 수정"
                    type="button"
                  >
                    <Settings aria-hidden="true" />
                  </button>
                </div>
                <button className="header-auth-button" onClick={handleSignOut} type="button">
                  <LogOut aria-hidden="true" />
                  <span>로그아웃</span>
                </button>
              </>
            ) : (
              <>
                <button className="header-auth-button" onClick={() => openAuthGuide('login')} type="button">
                  <LogIn aria-hidden="true" />
                  <span>로그인</span>
                </button>
                <button className="header-auth-button primary" onClick={() => openAuthGuide('signup')} type="button">
                  <UserRound aria-hidden="true" />
                  <span>회원가입</span>
                </button>
              </>
            )}
          </div>
        </div>
        <nav aria-label="주요 메뉴">
          {visibleTabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                className={activeTab === tab.id ? 'active' : ''}
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                type="button"
              >
                <Icon aria-hidden="true" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
      </header>

      <section className="hero">
        <div className="hero__content">
          <p className="eyebrow">{activeLabel}</p>
          <h1>우리나라 희귀질환 환자와 가족을 위한 커뮤니티</h1>
          <p className="hero__lead">
            질환별 정보, 최신 소식, 진료와 복지 경험, 회원 프로필을 한곳에서 관리할 수 있는 한국어
            커뮤니티입니다.
          </p>
          <div className="hero__actions">
            <button className="secondary" type="button" onClick={() => setActiveTab('board')}>
              게시판 보기
            </button>
          </div>
        </div>
      </section>

      <section className="notice" aria-label="의료 정보 주의사항">
        <AlertCircle aria-hidden="true" />
        <p>
          이 페이지는 정보 제공 목적입니다. 진단, 치료, 약물, 검사 결정은 반드시 담당 의료진과 상의해야 합니다.
        </p>
      </section>

      {activeTab === 'home' && <HomeView />}
      {activeTab === 'disease-search' && <DiseaseSearchView />}
      {activeTab === 'news' && <NewsView />}
      {activeTab === 'board' && <BoardView user={user} />}
      {activeTab === 'schedule' && <ScheduleView user={user} onRequireAuth={() => openAuthGuide('login')} />}
      {activeTab === 'signup' && (
        <SignupView
          authMessage={authMessage}
          isSupabaseConfigured={isSupabaseConfigured}
          nickname={nickname}
          oauthProviders={oauthProviders}
          onOAuthSignIn={handleOAuthSignIn}
          onSaveProfile={() => saveUserProfile()}
          onSignOut={handleSignOut}
          profileForm={profileForm}
          setNickname={setNickname}
          setProfileForm={setProfileForm}
          user={user}
        />
      )}
      {activeTab === 'profile' && (
        <ProfileView
          nickname={nickname}
          onPhotoChange={handlePhotoChange}
          onRequireAuth={() => openAuthGuide('login')}
          onSaveProfile={() => saveUserProfile()}
          onSignOut={handleSignOut}
          photoPreview={photoPreview}
          profileForm={profileForm}
          profileMessage={profileMessage}
          setNickname={setNickname}
          setProfileForm={setProfileForm}
          user={user}
        />
      )}

      <footer>
        <Users aria-hidden="true" />
        <span>국내 희귀질환 커뮤니티 초안 · 질환별 정보와 보호자 중심 자료로 계속 확장 예정</span>
      </footer>
    </main>
  );
}

function HomeView() {
  return (
    <>
      <section className="section">
        <div className="section__heading">
          <BookOpen aria-hidden="true" />
          <div>
            <p className="eyebrow">Overview</p>
            <h2>한눈에 보는 핵심</h2>
          </div>
        </div>
        <div className="fact-grid">
          {keyFacts.map((fact) => (
            <article className="card" key={fact}>
              <p>{fact}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section split">
        <div>
          <div className="section__heading compact">
            <FileText aria-hidden="true" />
            <div>
              <p className="eyebrow">Care</p>
              <h2>진료와 지원 준비 체크리스트</h2>
            </div>
          </div>
          <ul className="check-list">
            <li>진단명, 유전자 검사 결과, 영상/검사 기록을 정리</li>
            <li>해당 질환을 보는 전문 진료과와 희귀질환 전문기관 확인</li>
            <li>재활, 약물, 영양, 수면, 통증 등 동반 문제 기록</li>
            <li>산정특례, 의료비 지원, 장애 등록, 돌봄 지원 제도 확인</li>
          </ul>
        </div>
        <aside className="support-panel">
          <HeartHandshake aria-hidden="true" />
          <h2>가족에게 필요한 것</h2>
          <p>
            진료 기록, 검사 결과, 증상 변화, 치료 이력을 한곳에 모아두면 다음 진료와 상담에 도움이 됩니다.
          </p>
        </aside>
      </section>

      <section className="section">
        <div className="section__heading">
          <BookOpen aria-hidden="true" />
          <div>
            <p className="eyebrow">Sources</p>
            <h2>신뢰할 수 있는 자료</h2>
          </div>
        </div>
        <div className="source-list">
          {sources.map((source) => (
            <a className="source" href={source.href} target="_blank" rel="noreferrer" key={source.href}>
              <div>
                <strong>{source.label}</strong>
                <p>{source.description}</p>
              </div>
              <ChevronRight aria-hidden="true" />
            </a>
          ))}
        </div>
      </section>
    </>
  );
}

function ScheduleView({ user, onRequireAuth }: { user: User | null; onRequireAuth: () => void }) {
  if (!user) {
    return (
      <section className="section">
        <div className="empty-state auth-required">
          <strong>회원 전용 일정입니다</strong>
          <p>나의 일정은 Google 또는 Kakao 계정으로 로그인한 뒤 사용자별로 저장됩니다.</p>
          <button className="command-button" onClick={onRequireAuth} type="button">
            Google/Kakao로 가입 또는 로그인
          </button>
        </div>
      </section>
    );
  }

  return <AuthenticatedScheduleView key={user.id} user={user} />;
}

function AuthenticatedScheduleView({ user }: { user: User }) {
  const todayKey = toDateKey(new Date());
  const storageKey = useMemo(() => getScheduleStorageKey(user.id), [user.id]);
  const [monthDate, setMonthDate] = useState(() => new Date());
  const [selectedDate, setSelectedDate] = useState(todayKey);
  const [draftText, setDraftText] = useState('');
  const [entries, setEntries] = useState<Record<string, ScheduleEntry>>(() => {
    try {
      return JSON.parse(localStorage.getItem(storageKey) ?? '{}') as Record<string, ScheduleEntry>;
    } catch {
      return {};
    }
  });
  const [sharedEntries, setSharedEntries] = useState<SharedScheduleEntry[]>([]);
  const [shares, setShares] = useState<ScheduleShare[]>([]);
  const [memberSearch, setMemberSearch] = useState('');
  const [memberResults, setMemberResults] = useState<MemberProfile[]>([]);
  const [saveMessage, setSaveMessage] = useState('');
  const [savePopupMessage, setSavePopupMessage] = useState('');
  const [shareMessage, setShareMessage] = useState('');

  const calendarDays = useMemo(() => getCalendarDays(monthDate), [monthDate]);
  const selectedEntry = entries[selectedDate];
  const selectedImages = selectedEntry?.images ?? [];
  const selectedShares = shares.filter((share) => share.entry_id === selectedEntry?.id);
  const selectedSharedEntries = sharedEntries.filter((entry) => entry.dateKey === selectedDate);

  useEffect(() => {
    setDraftText(entries[selectedDate]?.text ?? '');
    setSaveMessage('');
    setShareMessage('');
    setSavePopupMessage('');
  }, [entries, selectedDate]);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(entries));
    } catch {
      setSaveMessage('이미지 용량이 커서 브라우저 저장 공간을 초과했습니다. 이미지를 줄여 다시 저장해 주세요.');
    }
  }, [entries, storageKey]);

  useEffect(() => {
    loadSchedules();
  }, [user.id]);

  useEffect(() => {
    const query = memberSearch.trim();
    if (!supabase || query.length < 2) {
      setMemberResults([]);
      return;
    }

    let isCurrent = true;
    supabase
      .from('profiles')
      .select('id,nickname,full_name')
      .neq('id', user.id)
      .or(`nickname.ilike.%${query}%,full_name.ilike.%${query}%`)
      .limit(8)
      .then(({ data, error }) => {
        if (!isCurrent) return;
        if (error) {
          setShareMessage('회원 검색 중 오류가 발생했습니다.');
          setMemberResults([]);
          return;
        }
        setMemberResults((data ?? []) as MemberProfile[]);
      });

    return () => {
      isCurrent = false;
    };
  }, [memberSearch, user.id]);

  async function loadSchedules() {
    if (!supabase) return;
    const { data: sessionData } = await supabase.auth.getSession();
    const token = sessionData.session?.access_token;
    if (!token) return;

    const response = await fetch('/api/schedules', {
      headers: { authorization: `Bearer ${token}` },
    });

    if (!response.ok) {
      setSaveMessage('일정 정보를 불러오지 못했습니다.');
      return;
    }

    const payload = await response.json();
    const ownRows = (payload.ownEntries ?? []) as ScheduleApiEntry[];
    const nextEntries: Record<string, ScheduleEntry> = {};
    for (const row of ownRows) {
      nextEntries[row.date_key] = {
        id: row.id,
        userId: row.user_id,
        text: row.text ?? '',
        images: row.images ?? [],
        updatedAt: row.updated_at,
      };
    }
    setEntries((current) => ({ ...current, ...nextEntries }));
    setShares((payload.shares ?? []) as ScheduleShare[]);

    setSharedEntries(
      ((payload.sharedEntries ?? []) as ScheduleApiEntry[]).map((row) => {
        const profile = row.ownerProfile;
        return {
          id: row.id,
          dateKey: row.date_key,
          ownerId: row.user_id,
          ownerNickname: profile?.nickname ?? '공유 회원',
          ownerName: profile?.full_name ?? null,
          text: row.text ?? '',
          images: row.images ?? [],
          updatedAt: row.updated_at,
        };
      }),
    );
  }

  function moveMonth(amount: number) {
    setMonthDate((current) => new Date(current.getFullYear(), current.getMonth() + amount, 1));
  }

  async function saveEntry(nextImages = selectedImages) {
    const nextText = draftText.trim();
    const nextEntry = nextText || nextImages.length > 0
      ? {
          id: selectedEntry?.id,
          userId: user.id,
          text: draftText,
          images: nextImages,
          updatedAt: new Date().toISOString(),
        }
      : null;

    setEntries((current) => {
      const next = { ...current };
      if (!nextEntry) {
        delete next[selectedDate];
        return next;
      }
      next[selectedDate] = nextEntry;
      return next;
    });

    if (!supabase) {
      setSaveMessage('현재 로그인한 계정 기준으로 이 브라우저에 저장되었습니다.');
      setSavePopupMessage(formatDailyRecordSavedMessage(selectedDate));
      return selectedEntry?.id ?? null;
    }
    const { data: sessionData } = await supabase.auth.getSession();
    const token = sessionData.session?.access_token;
    if (!token) return null;

    if (!nextEntry) {
      if (selectedEntry?.id) {
        const deleteResponse = await fetch('/api/schedules', {
          method: 'POST',
          headers: {
            authorization: `Bearer ${token}`,
            'content-type': 'application/json',
          },
          body: JSON.stringify({ id: selectedEntry.id, date_key: selectedDate, text: '', images: [] }),
        });
        if (!deleteResponse.ok) setSaveMessage('삭제 중 오류가 발생했습니다.');
      }
      setSaveMessage('삭제되었습니다.');
      await loadSchedules();
      return null;
    }

    const saveResponse = await fetch('/api/schedules', {
      method: 'POST',
      headers: {
        authorization: `Bearer ${token}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        id: selectedEntry?.id,
        date_key: selectedDate,
        text: draftText,
        images: nextImages,
      }),
    });

    if (!saveResponse.ok) {
      setSaveMessage('일정 저장 중 오류가 발생했습니다.');
      return null;
    }

    const { entry: data } = await saveResponse.json();
    if (!data) return null;
    setEntries((current) => ({
      ...current,
      [selectedDate]: {
        id: data.id,
        userId: data.user_id,
        text: data.text ?? '',
        images: data.images ?? [],
        updatedAt: data.updated_at,
      },
    }));
    setSaveMessage(formatDailyRecordSavedMessage(selectedDate));
    setSavePopupMessage(formatDailyRecordSavedMessage(selectedDate));
    await loadSchedules();
    return data.id as string;
  }

  async function handleImagesChange(event: React.ChangeEvent<HTMLInputElement>) {
    const loadedImages = await readImages(event.target.files);
    if (loadedImages.length === 0) return;
    const nextImages = [...selectedImages, ...loadedImages];
    saveEntry(nextImages);
    event.target.value = '';
  }

  function removeImage(index: number) {
    const nextImages = selectedImages.filter((_, imageIndex) => imageIndex !== index);
    saveEntry(nextImages);
  }

  async function shareSelectedEntry(profile: MemberProfile) {
    if (!supabase) return;
    let entryId: string | null | undefined = selectedEntry?.id;
    if (!entryId) {
      entryId = await saveEntry();
    }

    if (!entryId) {
      setShareMessage('먼저 해당 날짜의 일정을 저장한 뒤 공유해 주세요.');
      return;
    }

    const { data: sessionData } = await supabase.auth.getSession();
    const token = sessionData.session?.access_token;
    if (!token) return;
    const response = await fetch(`/api/schedules/${entryId}/share`, {
      method: 'POST',
      headers: {
        authorization: `Bearer ${token}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({ shared_with: profile.id }),
    });

    if (!response.ok) {
      setShareMessage(response.status === 409 ? '이미 공유된 회원입니다.' : '공유 중 오류가 발생했습니다.');
      return;
    }

    setMemberSearch('');
    setMemberResults([]);
    setShareMessage(`${profile.nickname} 회원에게 공유했습니다.`);
    await loadSchedules();
  }

  async function removeShare(shareId: string) {
    if (!supabase) return;
    const { data: sessionData } = await supabase.auth.getSession();
    const token = sessionData.session?.access_token;
    if (!token) return;
    const response = await fetch(`/api/schedule-shares/${shareId}`, {
      method: 'DELETE',
      headers: { authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      setShareMessage('공유 해제 중 오류가 발생했습니다.');
      return;
    }
    setShareMessage('공유를 해제했습니다.');
    await loadSchedules();
  }

  return (
    <section className="section schedule-layout">
      <div className="calendar-panel">
        <div className="section-toolbar">
          <div className="section__heading">
            <CalendarDays aria-hidden="true" />
            <div>
              <p className="eyebrow">My Calendar</p>
              <h2>나의 일정</h2>
            </div>
          </div>
          <div className="month-controls" aria-label="달 이동">
            <button type="button" onClick={() => moveMonth(-1)}>
              이전
            </button>
            <strong>
              {monthDate.getFullYear()}년 {monthDate.getMonth() + 1}월
            </strong>
            <button type="button" onClick={() => moveMonth(1)}>
              다음
            </button>
          </div>
        </div>

        <div className="calendar-grid" aria-label="진행상황 달력">
          {weekdays.map((weekday) => (
            <div className="weekday" key={weekday}>
              {weekday}
            </div>
          ))}
          {calendarDays.map((day) => {
            const hasEntry = Boolean(entries[day.key]?.text || entries[day.key]?.images.length);
            const hasSharedEntry = sharedEntries.some((entry) => entry.dateKey === day.key);
            return (
              <button
                className={[
                  'calendar-day',
                  day.inMonth ? '' : 'muted',
                  day.key === selectedDate ? 'selected' : '',
                  day.key === todayKey ? 'today' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                key={day.key}
                onClick={() => setSelectedDate(day.key)}
                type="button"
              >
                <span>{day.date.getDate()}</span>
                {hasEntry && <small>기록</small>}
                {!hasEntry && hasSharedEntry && <small>공유</small>}
              </button>
            );
          })}
        </div>
      </div>

      <aside className="day-editor">
        <div className="form-section-title">
          <FileText aria-hidden="true" />
          <div>
            <p className="eyebrow">Daily Record</p>
            <h2>{formatKoreanDate(selectedDate)}</h2>
          </div>
        </div>
        <label>
          진행상황
          <textarea
            placeholder="오늘의 증상, 컨디션, 복약, 재활, 병원 일정, 특이사항을 기록하세요."
            value={draftText}
            onChange={(event) => setDraftText(event.target.value)}
          />
        </label>

        <div className="image-uploader">
          <label className="upload-button">
            <ImagePlus aria-hidden="true" />
            이미지 추가
            <input accept="image/*" multiple onChange={handleImagesChange} type="file" />
          </label>
          <button className="command-button" onClick={() => saveEntry()} type="button">
            <Save aria-hidden="true" />
            저장
          </button>
        </div>

        {selectedImages.length > 0 && (
          <div className="schedule-images">
            {selectedImages.map((image, index) => (
              <figure key={`${image.slice(0, 32)}-${index}`}>
                <img alt={`${formatKoreanDate(selectedDate)} 기록 이미지 ${index + 1}`} src={image} />
                <button aria-label="이미지 삭제" onClick={() => removeImage(index)} type="button">
                  <Trash2 aria-hidden="true" />
                </button>
              </figure>
            ))}
          </div>
        )}

        <div className="share-panel">
          <div className="share-panel__title">
            <Share2 aria-hidden="true" />
            <strong>일정 공유</strong>
          </div>
          <label>
            회원 검색
            <input
              placeholder="회원 아이디 또는 이름 검색"
              value={memberSearch}
              onChange={(event) => setMemberSearch(event.target.value)}
            />
          </label>
          {memberResults.length > 0 && (
            <div className="member-results">
              {memberResults.map((profile) => (
                <button key={profile.id} onClick={() => shareSelectedEntry(profile)} type="button">
                  <UserPlus aria-hidden="true" />
                  <span>
                    <strong>{profile.nickname}</strong>
                    {profile.full_name && <small>{profile.full_name}</small>}
                  </span>
                </button>
              ))}
            </div>
          )}
          {selectedShares.length > 0 && (
            <div className="shared-members">
              {selectedShares.map((share) => (
                <span key={share.id}>
                  {share.profile?.nickname ?? '공유 회원'}
                  <button onClick={() => removeShare(share.id)} type="button">
                    해제
                  </button>
                </span>
              ))}
            </div>
          )}
          <p className="form-note">{shareMessage || '선택한 날짜 기록을 검색한 회원에게 공유할 수 있습니다.'}</p>
        </div>

        {selectedSharedEntries.length > 0 && (
          <div className="shared-entry-list">
            <strong>공유받은 일정</strong>
            {selectedSharedEntries.map((entry) => (
              <article className="shared-entry" key={entry.id}>
                <div>
                  <span>작성자</span>
                  <strong>{entry.ownerNickname}</strong>
                </div>
                {entry.text && <p>{entry.text}</p>}
                {entry.images.length > 0 && (
                  <div className="schedule-images compact">
                    {entry.images.map((image, index) => (
                      <figure key={`${entry.id}-${index}`}>
                        <img alt={`${entry.ownerNickname} 공유 일정 이미지 ${index + 1}`} src={image} />
                      </figure>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}

        <p className="form-note">{saveMessage || '저장한 일정은 내 계정에 저장되고, 공유한 회원에게만 보입니다.'}</p>
        {savePopupMessage && (
          <div className="save-popup-backdrop" role="presentation">
            <div aria-live="polite" className="save-popup" role="dialog" aria-label="저장 완료">
              <button
                aria-label="저장 완료 팝업 닫기"
                className="icon-button save-popup__close"
                onClick={() => setSavePopupMessage('')}
                type="button"
              >
                <X aria-hidden="true" />
              </button>
              <CalendarDays aria-hidden="true" />
              <strong>{savePopupMessage}</strong>
            </div>
          </div>
        )}
      </aside>
    </section>
  );
}

function NewsView() {
  const [newsItems, setNewsItems] = useState<NewsArticle[]>([]);
  const [newsMessage, setNewsMessage] = useState('');
  const [keywordInput, setKeywordInput] = useState('');
  const [selectedCountry, setSelectedCountry] = useState('all');
  const [selectedNewsCategory, setSelectedNewsCategory] = useState('all');
  const [selectedArticle, setSelectedArticle] = useState<NewsArticle | null>(null);
  const [selectedClinicalDrug, setSelectedClinicalDrug] = useState<string | null>(null);
  const [selectedArticleLoading, setSelectedArticleLoading] = useState(false);
  const [savedKeywords, setSavedKeywords] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(newsKeywordStorageKey) || '[]');
    } catch {
      return [];
    }
  });

  const countryOptions = useMemo(() => {
    const counts = new Map<string, number>();
    newsItems.forEach((item) => {
      const country = getNewsCountry(item);
      counts.set(country.id, (counts.get(country.id) ?? 0) + 1);
    });

    return countryOptionOrder.map((id) => ({ ...newsCountries[id], count: counts.get(id) ?? 0 }));
  }, [newsItems]);

  const filteredNewsItems = useMemo(() => {
    return newsItems.filter((item) => {
      const country = getNewsCountry(item);
      if (selectedCountry !== 'all' && country.id !== selectedCountry) return false;
      const category = getNewsCategory(item);
      if (selectedNewsCategory !== 'all' && category !== selectedNewsCategory) return false;
      if (savedKeywords.length === 0) return true;

      const haystack = [
        item.title_original,
        item.title_ko,
        item.summary_ko,
        item.content_ko,
        ...(item.keywords ?? []).filter((keyword) => !keyword.startsWith('source:')),
      ]
        .join(' ')
        .toLowerCase();
      return savedKeywords.some((keyword) => keywordMatchesText(keyword, haystack));
    });
  }, [newsItems, savedKeywords, selectedCountry, selectedNewsCategory]);

  const clinicalTimelineGroups = useMemo(() => {
    if (selectedNewsCategory !== 'clinical_trial' || savedKeywords.length === 0) return [];
    return buildClinicalTimelineGroups(filteredNewsItems);
  }, [filteredNewsItems, savedKeywords.length, selectedNewsCategory]);

  const selectedClinicalDrugGroup = useMemo(() => {
    return clinicalTimelineGroups.find((group) => group.drugName === selectedClinicalDrug) ?? clinicalTimelineGroups[0] ?? null;
  }, [clinicalTimelineGroups, selectedClinicalDrug]);

  const selectedCountryInfo = selectedCountry === 'all' ? null : newsCountries[selectedCountry] || defaultNewsCountry;

  function saveKeyword() {
    const nextKeyword = keywordInput.trim().toLowerCase();
    if (!nextKeyword || savedKeywords.includes(nextKeyword)) return;
    const nextKeywords = [...savedKeywords, nextKeyword];
    setSavedKeywords(nextKeywords);
    localStorage.setItem(newsKeywordStorageKey, JSON.stringify(nextKeywords));
    setKeywordInput('');
  }

  function removeKeyword(keyword: string) {
    const nextKeywords = savedKeywords.filter((item) => item !== keyword);
    setSavedKeywords(nextKeywords);
    localStorage.setItem(newsKeywordStorageKey, JSON.stringify(nextKeywords));
  }

  async function loadNewsFromServer() {
    const response = await fetch('/api/news?limit=5000');
    if (!response.ok) throw new Error('서버 뉴스 저장소를 불러오지 못했습니다.');
    const payload = await response.json();
    setNewsItems(payload.items ?? []);
    if (payload.storage === 'file') {
      setNewsMessage('Supabase 스키마 적용 전이라 서버 임시 저장소의 뉴스를 표시하고 있습니다.');
    }
  }

  useEffect(() => {
    loadNewsFromServer().catch((error) => setNewsMessage(error.message));
  }, []);

  useEffect(() => {
    if (!selectedArticle) return;

    const controller = new AbortController();
    setSelectedArticleLoading(true);
    fetch(`/api/news-detail?url=${encodeURIComponent(selectedArticle.url)}`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('기사 본문을 불러오지 못했습니다.');
        return response.json();
      })
      .then((payload) => {
        const nextItem = payload.item as NewsArticle;
        setSelectedArticle(nextItem);
        setNewsItems((current) => current.map((item) => (item.url === nextItem.url ? { ...item, ...nextItem } : item)));
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setNewsMessage(error.message);
      })
      .finally(() => setSelectedArticleLoading(false));

    return () => controller.abort();
  }, [selectedArticle?.url]);

  return (
    <section className="section">
      <div className="section__heading">
        <Newspaper aria-hidden="true" />
        <div>
          <p className="eyebrow">News</p>
          <h2>뉴스와 공지</h2>
        </div>
      </div>
      <div className="keyword-panel">
        <div className="news-filter-grid">
          <label>
            국가별 뉴스
            <span className="country-filter-row">
              <select value={selectedCountry} onChange={(event) => setSelectedCountry(event.target.value)}>
                <option value="all">전체 국가</option>
                {countryOptions.map((country) => (
                  <option key={country.id} value={country.id}>
                    {country.name} {country.emoji} ({country.count})
                  </option>
                ))}
              </select>
              {selectedCountryInfo && (
                <span className="selected-country" aria-label={`${selectedCountryInfo.name} 선택됨`}>
                  {selectedCountryInfo.flagCode ? (
                    <img
                      alt=""
                      src={`https://flagcdn.com/w40/${selectedCountryInfo.flagCode}.png`}
                      width="40"
                      height="30"
                    />
                  ) : (
                    <span aria-hidden="true">{selectedCountryInfo.emoji}</span>
                  )}
                  {selectedCountryInfo.name}
                </span>
              )}
            </span>
          </label>
          <label>
            뉴스 카테고리
            <select value={selectedNewsCategory} onChange={(event) => setSelectedNewsCategory(event.target.value)}>
              {newsCategoryOptions.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label>
          관심 키워드
          <span className="keyword-input-row">
            <input
              placeholder="예: ppp2r5d, gene therapy"
              value={keywordInput}
              onChange={(event) => setKeywordInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  saveKeyword();
                }
              }}
            />
            <button className="command-button" onClick={saveKeyword} type="button">
              <Search aria-hidden="true" />
              등록
            </button>
          </span>
        </label>
        {savedKeywords.length > 0 && (
          <div className="keyword-chips" aria-label="등록된 뉴스 키워드">
            {savedKeywords.map((keyword) => (
              <button key={keyword} onClick={() => removeKeyword(keyword)} type="button">
                {keyword}
                <X aria-hidden="true" />
              </button>
            ))}
          </div>
        )}
      </div>
      {selectedNewsCategory === 'clinical_trial' && savedKeywords.length > 0 && clinicalTimelineGroups.length > 0 && (
        <div className="clinical-timeline" aria-label="임상시험 개발 타임라인">
          <div className="clinical-timeline__header">
            <div>
              <p className="eyebrow">Clinical Timeline</p>
              <h3>{savedKeywords.join(', ')} 약별 임상 개발 흐름</h3>
            </div>
            <span>{clinicalTimelineGroups.length}개 약/중재</span>
          </div>
          <div className="clinical-timeline__groups">
            {clinicalTimelineGroups.map((group) => (
              <div className="clinical-drug" key={group.drugName}>
                <button
                  className={`clinical-drug__header${selectedClinicalDrugGroup?.drugName === group.drugName ? ' active' : ''}`}
                  onClick={() => setSelectedClinicalDrug(group.drugName)}
                  type="button"
                >
                  <strong>{group.drugName}</strong>
                  <span>{group.summary}</span>
                </button>
                <div className="clinical-timeline__rail">
                  {group.items.map((item) => (
                    <button
                      className="clinical-timeline__node"
                      key={item.id}
                      onClick={() => setSelectedArticle(item.article)}
                      type="button"
                    >
                      <span className="clinical-timeline__year">{item.yearLabel}</span>
                      <span className="clinical-timeline__dot" aria-hidden="true" />
                      <span className="clinical-timeline__card">
                        <strong>{item.phaseLabel}</strong>
                        <small>{item.statusLabel}</small>
                        <span>{item.title}</span>
                        <small>{item.source}</small>
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
          {selectedClinicalDrugGroup && (
            <div className="clinical-drug-detail">
              <div>
                <p className="eyebrow">Drug Detail</p>
                <h4>{selectedClinicalDrugGroup.drugName}</h4>
              </div>
              <p>{selectedClinicalDrugGroup.effectNote}</p>
              <dl>
                <div>
                  <dt>단계</dt>
                  <dd>{selectedClinicalDrugGroup.items.map((item) => item.phaseLabel).join(' → ')}</dd>
                </div>
                <div>
                  <dt>상태</dt>
                  <dd>{selectedClinicalDrugGroup.items[selectedClinicalDrugGroup.items.length - 1]?.statusLabel}</dd>
                </div>
                <div>
                  <dt>근거</dt>
                  <dd>{selectedClinicalDrugGroup.items[selectedClinicalDrugGroup.items.length - 1]?.source}</dd>
                </div>
              </dl>
              <button
                className="command-button"
                onClick={() => {
                  const latestArticle = selectedClinicalDrugGroup.items[selectedClinicalDrugGroup.items.length - 1]?.article;
                  if (latestArticle) setSelectedArticle(latestArticle);
                }}
                type="button"
              >
                상세 원문/번역 보기
              </button>
            </div>
          )}
        </div>
      )}
      {filteredNewsItems.length > 0 ? (
        <div className="news-list">
          {filteredNewsItems.map((item) => (
            <article className="news-item" key={item.id}>
              <button className="news-item__button" onClick={() => setSelectedArticle(item)} type="button">
                <time>{item.published_at ? new Date(item.published_at).toLocaleDateString('ko-KR') : '수집 자료'}</time>
                <h3>{item.title_ko || item.title_original}</h3>
                {item.summary_ko && <p>{item.summary_ko}</p>}
                <p className="news-source">
                  <span className={`news-category news-category--${getNewsCategory(item)}`}>
                    {getNewsCategoryLabel(getNewsCategory(item))}
                  </span>
                  <span className="news-country">
                    {getNewsCountry(item).flagCode ? (
                      <img
                        alt=""
                        src={`https://flagcdn.com/w20/${getNewsCountry(item).flagCode}.png`}
                        width="20"
                        height="15"
                      />
                    ) : (
                      <span aria-hidden="true">{getNewsCountry(item).emoji}</span>
                    )}
                    {getNewsCountry(item).name}
                  </span>
                  출처: {item.source_name}
                </p>
              </button>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState
          title={newsItems.length > 0 ? '선택한 조건과 일치하는 뉴스가 없습니다' : '등록된 뉴스가 없습니다'}
          description={
            newsMessage ||
            (newsItems.length > 0
              ? '다른 국가를 선택하거나 기존 키워드를 지우면 더 많은 뉴스를 볼 수 있습니다.'
              : '매일 00:00 자동 크롤링 후 Supabase에 저장된 뉴스만 표시됩니다.')
          }
        />
      )}
      {selectedArticle && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSelectedArticle(null);
          }}
        >
          <article className="article-modal" role="dialog" aria-modal="true" aria-labelledby="article-modal-title">
            <div className="article-modal__header">
              <div>
                <time>
                  {selectedArticle.published_at
                    ? new Date(selectedArticle.published_at).toLocaleDateString('ko-KR')
                    : '수집 자료'}
                </time>
                <h2 id="article-modal-title">{selectedArticle.title_ko || selectedArticle.title_original}</h2>
                <p>출처: {selectedArticle.source_name}</p>
              </div>
              <button aria-label="닫기" className="icon-button" onClick={() => setSelectedArticle(null)} type="button">
                <X aria-hidden="true" />
              </button>
            </div>
            <div className="article-modal__body">
              {selectedArticleLoading && <p className="article-modal__loading">원문을 열어 전체 번역문을 가져오는 중입니다.</p>}
              {(selectedArticle.content_ko || selectedArticle.summary_ko || '번역된 본문을 아직 가져오지 못했습니다.')
                .split(/\n{2,}/)
                .filter(Boolean)
                .map((paragraph) => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
            </div>
            <div className="article-modal__actions">
              <a href={selectedArticle.url} target="_blank" rel="noreferrer">
                원문 보기
              </a>
              <button className="command-button" onClick={() => setSelectedArticle(null)} type="button">
                닫기
              </button>
            </div>
          </article>
        </div>
      )}
    </section>
  );
}

function DiseaseSearchView() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<KrdisDiseaseResult[]>([]);
  const [selectedGene, setSelectedGene] = useState('all');
  const [selectedDisease, setSelectedDisease] = useState<KrdisDiseaseResult | null>(null);
  const [detail, setDetail] = useState<KrdisDiseaseDetail | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [message, setMessage] = useState('');

  const searchedGene = useMemo(() => {
    const value = query.trim().toUpperCase();
    return /^[A-Z0-9-]{3,}$/.test(value) && /[0-9]/.test(value) ? value : '';
  }, [query]);

  const geneFilters = useMemo(() => {
    const genes = new Set<string>();
    if (searchedGene) genes.add(searchedGene);
    results.forEach((item) => item.gene_symbols?.forEach((gene) => genes.add(gene)));
    return Array.from(genes);
  }, [results, searchedGene]);

  const filteredResults = useMemo(() => {
    if (selectedGene === 'all') return results;
    return results.filter((item) => {
      const haystack = [item.name_ko, item.name_en, ...(item.gene_symbols ?? []), ...(item.aliases ?? [])].join(' ').toUpperCase();
      return haystack.includes(selectedGene);
    });
  }, [results, selectedGene]);

  useEffect(() => {
    const trimmedQuery = query.trim();
    if (trimmedQuery.length < 2) {
      setResults([]);
      setMessage('');
      setSelectedGene('all');
      return;
    }

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => {
      setIsSearching(true);
      fetch(`/api/krdis-diseases?q=${encodeURIComponent(trimmedQuery)}`, { signal: controller.signal })
        .then((response) => {
          if (!response.ok) throw new Error('KRDIS 희귀병 검색을 불러오지 못했습니다.');
          return response.json();
        })
        .then((payload: { items?: KrdisDiseaseResult[] }) => {
          setResults(payload.items ?? []);
          setSelectedGene('all');
          setMessage((payload.items ?? []).length > 0 ? '' : '검색 결과가 없습니다.');
        })
        .catch((error) => {
          if (error.name !== 'AbortError') setMessage(error.message);
        })
        .finally(() => setIsSearching(false));
    }, 250);

    return () => {
      window.clearTimeout(timeoutId);
      controller.abort();
    };
  }, [query]);

  useEffect(() => {
    if (!selectedDisease) {
      setDetail(null);
      return;
    }

    const controller = new AbortController();
    setIsLoadingDetail(true);
    fetch(`/api/krdis-disease-detail?url=${encodeURIComponent(selectedDisease.url)}`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('KRDIS 상세 정보를 불러오지 못했습니다.');
        return response.json();
      })
      .then((payload: { item?: KrdisDiseaseDetail }) => setDetail(payload.item ?? null))
      .catch((error) => {
        if (error.name !== 'AbortError') setMessage(error.message);
      })
      .finally(() => setIsLoadingDetail(false));

    return () => controller.abort();
  }, [selectedDisease]);

  return (
    <section className="section">
      <div className="section-toolbar">
        <div className="section__heading">
          <Search aria-hidden="true" />
          <div>
            <p className="eyebrow">Rare Disease Search</p>
            <h2>희귀병 검색</h2>
          </div>
        </div>
        <span className="toolbar-note">KRDIS 저장 정보 기준</span>
      </div>

      <div className="keyword-panel">
        <label>
          희귀병 이름 검색
          <span className="keyword-input-row">
            <input
              placeholder="예: 크론병, 혈우병, 모야모야병"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </span>
        </label>
        {geneFilters.length > 0 && (
          <div className="gene-filter" aria-label="유전자별 결과 분류">
            <button className={selectedGene === 'all' ? 'active' : ''} onClick={() => setSelectedGene('all')} type="button">
              전체
            </button>
            {geneFilters.map((gene) => (
              <button className={selectedGene === gene ? 'active' : ''} key={gene} onClick={() => setSelectedGene(gene)} type="button">
                {gene}
              </button>
            ))}
          </div>
        )}
      </div>

      {message && <p className="form-note board-note">{message}</p>}

      {query.trim().length < 2 ? (
        <EmptyState title="검색어를 입력해 주세요" description="두 글자 이상 입력하면 KRDIS 희귀질환 정보에서 검색합니다." />
      ) : isSearching ? (
        <EmptyState title="검색 중입니다" description="KRDIS 자료를 확인하고 있습니다." />
      ) : (
        <div className="board-list">
          {filteredResults.map((item) => (
            <article className="board-row article-row disease-result" key={item.id}>
              <div>
                <h3>{item.name_en || item.name_ko}</h3>
                {item.name_ko && <p className="disease-result__ko">{item.name_ko}</p>}
                {item.name_en && item.name_ko && <p className="disease-result__en">{item.name_en}</p>}
                <div className="disease-meta">
                  {item.gene_symbols?.length > 0
                    ? item.gene_symbols.map((gene) => <span key={gene}>{gene}</span>)
                    : searchedGene && <span>{searchedGene}</span>}
                  {item.category && <span>{item.category}</span>}
                  {item.kcd_code && <span>KCD {item.kcd_code}</span>}
                  <span>출처: {item.source}</span>
                </div>
                {item.aliases && item.aliases.length > 0 && <p className="disease-result__aliases">AKA {item.aliases.join(', ')}</p>}
              </div>
              <button className="command-button" onClick={() => setSelectedDisease(item)} type="button">
                정보 보기
              </button>
            </article>
          ))}
        </div>
      )}

      {selectedDisease && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSelectedDisease(null);
          }}
        >
          <article className="article-modal" role="dialog" aria-modal="true" aria-labelledby="disease-modal-title">
            <div className="article-modal__header">
              <div>
                <time>{detail?.kid_code ?? 'KRDIS'}</time>
                <h2 id="disease-modal-title">
                  {detail?.name_en || selectedDisease.name_en || detail?.name_ko || selectedDisease.name_ko}
                </h2>
                {(detail?.name_ko || selectedDisease.name_ko) && <p>{detail?.name_ko || selectedDisease.name_ko}</p>}
                {((detail?.gene_symbols?.length ?? 0) > 0 || searchedGene) && (
                  <div className="disease-meta modal-meta">
                    {(detail?.gene_symbols?.length ? detail.gene_symbols : [searchedGene]).filter(Boolean).map((gene) => (
                      <span key={gene}>{gene}</span>
                    ))}
                  </div>
                )}
              </div>
              <button aria-label="닫기" className="icon-button" onClick={() => setSelectedDisease(null)} type="button">
                <X aria-hidden="true" />
              </button>
            </div>
            <div className="article-modal__body">
              {isLoadingDetail && <p className="article-modal__loading">KRDIS 상세 정보를 가져오는 중입니다.</p>}
              {!isLoadingDetail && detail?.sections.length === 0 && (
                <p>상세 설명을 찾지 못했습니다. 아래 원문에서 최신 정보를 확인해 주세요.</p>
              )}
              {detail?.sections.map((section) => (
                <section className="disease-detail-section" key={`${section.title_ko}-${section.title_en ?? ''}`}>
                  <h3>{section.title_ko}</h3>
                  {section.title_en && <strong>{section.title_en}</strong>}
                  <p>{section.body}</p>
                </section>
              ))}
            </div>
            <div className="article-modal__actions">
              <a href={selectedDisease.url} target="_blank" rel="noreferrer">
                KRDIS 원문 보기
              </a>
              <button className="command-button" onClick={() => setSelectedDisease(null)} type="button">
                닫기
              </button>
            </div>
          </article>
        </div>
      )}
    </section>
  );
}

function BoardView({ user }: { user: User | null }) {
  const [notices, setNotices] = useState<NoticePost[]>([]);
  const [noticeDraft, setNoticeDraft] = useState({ title: '', body: '' });
  const [boardMessage, setBoardMessage] = useState('');

  useEffect(() => {
    if (!supabase) {
      setBoardMessage('Supabase 설정이 필요합니다.');
      return;
    }

    supabase
      .from('notice_posts')
      .select('id, title, body, pinned, created_at')
      .order('pinned', { ascending: false })
      .order('created_at', { ascending: false })
      .limit(50)
      .then(({ data, error }) => {
        if (error) {
          setBoardMessage(`공지 게시판을 불러오지 못했습니다: ${error.message}`);
          return;
        }

        setNotices(data ?? []);
      });
  }, []);

  async function saveNotice() {
    if (!supabase || !user || !noticeDraft.title.trim() || !noticeDraft.body.trim()) return;

    const { error } = await supabase.from('notice_posts').insert({
      user_id: user.id,
      title: noticeDraft.title.trim(),
      body: noticeDraft.body.trim(),
    });

    if (error) {
      setBoardMessage(`공지 저장 실패: ${error.message}`);
      return;
    }

    setNoticeDraft({ title: '', body: '' });
    const { data } = await supabase
      .from('notice_posts')
      .select('id, title, body, pinned, created_at')
      .order('pinned', { ascending: false })
      .order('created_at', { ascending: false })
      .limit(50);
    setNotices(data ?? []);
  }

  return (
    <section className="section">
      <div className="section-toolbar">
        <div className="section__heading">
          <MessageCircle aria-hidden="true" />
          <div>
            <p className="eyebrow">Board</p>
            <h2>게시판</h2>
          </div>
        </div>
        <span className="toolbar-note">회원 공지 게시판</span>
      </div>

      {!user && (
        <EmptyState title="회원 전용 게시판입니다" description="게시글 읽기, 작성, 댓글은 로그인한 회원만 사용할 수 있습니다." />
      )}

      {user && boardMessage && <p className="form-note board-note">{boardMessage}</p>}

      {user && (
        <div className="board-content">
          <form className="form-panel board-form">
            <label>
              공지 제목
              <input
                value={noticeDraft.title}
                onChange={(event) => setNoticeDraft((current) => ({ ...current, title: event.target.value }))}
              />
            </label>
            <label>
              공지 내용
              <textarea
                value={noticeDraft.body}
                onChange={(event) => setNoticeDraft((current) => ({ ...current, body: event.target.value }))}
              />
            </label>
            <button
              className="command-button wide"
              disabled={!noticeDraft.title.trim() || !noticeDraft.body.trim()}
              onClick={saveNotice}
              type="button"
            >
              공지 저장
            </button>
          </form>

          {notices.length > 0 ? (
            <div className="board-list">
              {notices.map((notice) => (
                <article className="board-row article-row" key={notice.id}>
                  <div>
                    <h3>
                      {notice.pinned && <span className="notice-pin">고정</span>}
                      {notice.title}
                    </h3>
                    <p>{new Date(notice.created_at).toLocaleDateString('ko-KR')}</p>
                    <p>{notice.body}</p>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title="등록된 공지가 없습니다" description="공지 게시판에 아직 글이 없습니다." />
          )}
        </div>
      )}
    </section>
  );
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{description}</p>
    </div>
  );
}

function SignupView({
  authMessage,
  isSupabaseConfigured,
  nickname,
  oauthProviders,
  onOAuthSignIn,
  onSaveProfile,
  onSignOut,
  profileForm,
  setNickname,
  setProfileForm,
  user,
}: {
  authMessage: string;
  isSupabaseConfigured: boolean;
  nickname: string;
  oauthProviders: OAuthProviderStatus | null;
  onOAuthSignIn: (provider: 'google' | 'kakao') => void;
  onSaveProfile: () => void;
  onSignOut: () => void;
  profileForm: ProfileFormState;
  setNickname: React.Dispatch<React.SetStateAction<string>>;
  setProfileForm: React.Dispatch<React.SetStateAction<ProfileFormState>>;
  user: User | null;
}) {
  return (
    <section className="section account-layout" id="account-login">
      <div>
        <div className="section__heading">
          <UserRound aria-hidden="true" />
          <div>
            <p className="eyebrow">Account</p>
            <h2>로그인 / 회원가입</h2>
          </div>
        </div>
        {!user && (
          <div className="auth-status">
            <LogIn aria-hidden="true" />
            <div>
              <strong>소셜 계정으로 계속하기</strong>
              <p>아래 Google 또는 Kakao 버튼을 누르면 로그인 화면으로 이동합니다.</p>
            </div>
          </div>
        )}
        {user && (
          <div className="auth-status">
            <ShieldCheck aria-hidden="true" />
            <div>
              <strong>로그인됨</strong>
              <p>{user.email ?? '소셜 계정으로 로그인한 회원'}</p>
            </div>
          </div>
        )}
        <div className="social-buttons">
          <button
            disabled={!isSupabaseConfigured || oauthProviders?.google.enabled === false}
            onClick={() => onOAuthSignIn('google')}
            type="button"
          >
            Google 계정으로 계속
            {oauthProviders?.google.enabled === false && <small>Provider 설정 필요</small>}
          </button>
          <button
            disabled={!isSupabaseConfigured || oauthProviders?.kakao.enabled === false}
            onClick={() => onOAuthSignIn('kakao')}
            type="button"
          >
            Kakao 계정으로 계속
            {oauthProviders?.kakao.enabled === false && <small>Provider 설정 필요</small>}
          </button>
        </div>
        <p className="form-note">
          {authMessage || 'OAuth 제공자에서 이메일과 기본 프로필을 받고, 사이트 닉네임은 별도로 저장합니다.'}
        </p>
      </div>
      {user ? (
        <form className="form-panel">
          <label>
            사이트 닉네임
            <input value={nickname} onChange={(event) => setNickname(event.target.value)} />
          </label>
          <label>
            이메일 공개 범위
            <select
              value={profileForm.email_visibility}
              onChange={(event) =>
                setProfileForm((current) => ({ ...current, email_visibility: event.target.value }))
              }
            >
              <option value="private">비공개</option>
              <option value="members">회원에게만 공개</option>
              <option value="public">전체 공개</option>
            </select>
          </label>
          <label className="checkbox-row">
            <input type="checkbox" defaultChecked />
            <span>서비스 이용약관과 개인정보 처리방침에 동의합니다.</span>
          </label>
          <div className="inline-actions">
            <button className="command-button wide" onClick={onSaveProfile} type="button">
              가입 정보 저장
            </button>
            <button className="secondary-command wide" onClick={onSignOut} type="button">
              로그아웃
            </button>
          </div>
        </form>
      ) : (
        <div className="form-panel auth-required">
          <ShieldCheck aria-hidden="true" />
          <strong>로그인 후 회원정보를 저장할 수 있습니다</strong>
          <p>Google 계정으로 먼저 로그인하면 기본정보와 프로필 사진 변경 화면이 열립니다.</p>
        </div>
      )}
    </section>
  );
}

function ProfileView({
  nickname,
  setNickname,
  profileForm,
  setProfileForm,
  user,
  photoPreview,
  onPhotoChange,
  onRequireAuth,
  onSaveProfile,
  onSignOut,
  profileMessage,
}: {
  nickname: string;
  setNickname: React.Dispatch<React.SetStateAction<string>>;
  profileForm: ProfileFormState;
  setProfileForm: React.Dispatch<React.SetStateAction<ProfileFormState>>;
  user: User | null;
  photoPreview: string;
  onPhotoChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onRequireAuth: () => void;
  onSaveProfile: () => void;
  onSignOut: () => void;
  profileMessage: string;
}) {
  if (!user) {
    return (
      <section className="section">
        <div className="empty-state auth-required">
          <ShieldCheck aria-hidden="true" />
          <strong>회원정보는 로그인 후 이용할 수 있습니다</strong>
          <p>Google 또는 Kakao 계정으로 로그인하면 기본정보 저장과 프로필 사진 변경을 사용할 수 있습니다.</p>
          <button className="command-button" onClick={onRequireAuth} type="button">
            <LogIn aria-hidden="true" />
            로그인 / 회원가입
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="section profile-layout">
      <aside className="profile-summary">
        <div className="avatar">
          {photoPreview ? <img src={photoPreview} alt="프로필 미리보기" /> : <UserRound aria-hidden="true" />}
        </div>
        <strong>{nickname || '닉네임 미설정'}</strong>
        <p>{user ? user.email ?? 'Google 또는 Kakao 계정으로 로그인한 회원' : '로그인 후 회원정보를 저장할 수 있습니다.'}</p>
        <label className="upload-button">
          <Camera aria-hidden="true" />
          프로필 사진 변경
          <input accept="image/*" onChange={onPhotoChange} type="file" />
        </label>
        {user && (
          <button className="secondary-command wide" onClick={onSignOut} type="button">
            로그아웃
          </button>
        )}
      </aside>

      <form className="form-panel profile-form">
        <div className="form-section-title">
          <UserRound aria-hidden="true" />
          <h2>기본 정보</h2>
        </div>
        <div className="form-grid">
          <label>
            닉네임
            <input value={nickname} onChange={(event) => setNickname(event.target.value)} />
          </label>
          <label>
            이름
            <input
              placeholder="실명 또는 보호자 이름"
              value={profileForm.full_name}
              onChange={(event) => setProfileForm((current) => ({ ...current, full_name: event.target.value }))}
            />
          </label>
          <label>
            이메일
            <input placeholder="user@example.com" readOnly type="email" value={user?.email ?? ''} />
          </label>
          <label>
            휴대폰 번호
            <input
              placeholder="010-0000-0000"
              value={profileForm.phone}
              onChange={(event) => setProfileForm((current) => ({ ...current, phone: event.target.value }))}
            />
          </label>
          <label>
            생년월일
            <input
              type="date"
              value={profileForm.birth_date}
              onChange={(event) => setProfileForm((current) => ({ ...current, birth_date: event.target.value }))}
            />
          </label>
          <label>
            거주 지역
            <input
              placeholder="예: 서울특별시"
              value={profileForm.region}
              onChange={(event) => setProfileForm((current) => ({ ...current, region: event.target.value }))}
            />
          </label>
        </div>

        <div className="form-section-title">
          <HeartHandshake aria-hidden="true" />
          <h2>커뮤니티 정보</h2>
        </div>
        <div className="form-grid">
          <label>
            환자와의 관계
            <select
              value={profileForm.relationship}
              onChange={(event) => setProfileForm((current) => ({ ...current, relationship: event.target.value }))}
            >
              <option value="guardian">보호자</option>
              <option value="family">가족</option>
              <option value="patient">본인</option>
              <option value="expert">의료/지원 전문가</option>
            </select>
          </label>
          <label>
            관심 주제
            <select
              value={profileForm.topic}
              onChange={(event) => setProfileForm((current) => ({ ...current, topic: event.target.value }))}
            >
              <option value="care">진료와 재활</option>
              <option value="research">연구 자료</option>
              <option value="community">가족 커뮤니티</option>
            </select>
          </label>
          <label className="full">
            자기소개
            <textarea
              placeholder="게시판 프로필에 표시할 간단한 소개를 입력하세요."
              value={profileForm.bio}
              onChange={(event) => setProfileForm((current) => ({ ...current, bio: event.target.value }))}
            />
          </label>
        </div>

        <div className="settings-list">
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={profileForm.notification_opt_in}
              onChange={(event) =>
                setProfileForm((current) => ({ ...current, notification_opt_in: event.target.checked }))
              }
            />
            <span>
              <Bell aria-hidden="true" />
              새 뉴스와 댓글 알림 받기
            </span>
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={profileForm.keep_health_private}
              onChange={(event) =>
                setProfileForm((current) => ({ ...current, keep_health_private: event.target.checked }))
              }
            />
            <span>
              <Lock aria-hidden="true" />
              민감한 건강 정보는 기본 비공개로 유지
            </span>
          </label>
        </div>

        <button className="command-button wide" disabled={!user} onClick={onSaveProfile} type="button">
          회원정보 저장
        </button>
        <p className="form-note">{profileMessage || 'Google 또는 Kakao 로그인 후 회원정보를 저장할 수 있습니다.'}</p>
      </form>
    </section>
  );
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
