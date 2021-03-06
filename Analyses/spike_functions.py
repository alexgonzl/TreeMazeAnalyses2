import numpy as np
from scipy import stats, spatial, signal

"""
Functions for handling clusters and spike trains.
    ->  get_session_* functions require an instance of SubjectSessionInfo to work
    ->  other functions are auxiliary to the get_session_*, but can be used independently 
        the appropriate input.
        
- last edit: 8.6.20 -ag
"""


def get_session_spikes(session_info):
    """
    Wrapper function to obtain all the spikes from all the curated clusters for the specified session.
    :param SubjectSessionInfo session_info: instance of class SubjectInfo for a particular subject
    :return spikes, wfi. dictionaries separated with cell and mua keys, containing spike trains and waveform information
    """
    session_paths = session_info.paths
    params = session_info.params

    clusters = session_info.clusters
    spikes = {'Cell': {'n_units': 0}, 'Mua': {'n_units': 0}}
    wfi = {'Cell': {}, 'Mua': {}}
    for tt in clusters['curated_TTs']:
        unit_ids = {'Cell': {}, 'Mua': {}}
        n_tt_units = 0
        for ut in ['Cell', 'Mua']:
            try:  # when loading subject_info keys are strings
                unit_ids[ut] = clusters[ut.lower() + '_IDs'][str(tt)]
            except KeyError:  # if creating new dict, keys can be integers not strings
                unit_ids[ut] = clusters[ut.lower() + '_IDs'][tt]
            n_tt_units += len(unit_ids[ut])

        # if there are clusters, load data and get the spikes
        if n_tt_units > 0:
            tt_dat = np.load(session_paths['PreProcessed'] / 'tt_{}.npy'.format(tt))
            sort_dir = session_info.get_sorted_tt_dir(tt)
            spk_times = np.load(sort_dir / 'spike_times.npy')
            cluster_spks = np.load(sort_dir / 'spike_clusters.npy')
            for ut in ['Cell', 'Mua']:
                spikes[ut], wfi[ut] = _get_tt_spikes(tt, unit_ids[ut], tt_dat, spk_times,
                                                     cluster_spks, params, spikes[ut], wfi[ut])

    return spikes, wfi


def get_session_binned_spikes(session_info, spike_trains=None):
    """
    :param session_info session_info: instance of SubjectInfo for a particular subject
    :param np.ndarray spike_trains: if not provided, these are computed or loaded
    :returns: np.ndarray bin_spikes: shape n_clusters x n_bin_samps. simply the spike counts for each cluster/bin
    """
    time_step = session_info.params['time_step']

    if spike_trains is None:
        spike_trains, _, _ = session_info.get_spikes()

    # bin spikes
    time_orig = session_info.get_time('orig')
    time_resamp = session_info.get_time()

    bin_spikes = get_bin_spikes(spike_trains, time_resamp, time_orig, time_step=time_step)

    assert np.array([len(x) for x in spike_trains]).sum() == bin_spikes.sum(), \
        'Check sum of spikes failed. Likely spikes on the edges of the recording.'

    return bin_spikes


def get_session_fr(session_info, bin_spikes=None):
    """
    Get the firing rate for all the clusters in the session, from the binned spikes
    :param SubjectInfo session_info: instance of class SubjectInfo for a particular subject
    :param np.ndarray bin_spikes: shape [n_clusters x n_timebins]
    :return: np.ndarray neural_data: firing rate shape [n_clusters x n_timebins]
    """

    time_step = session_info.params['time_step']
    temporal_smoothing = session_info.params['fr_temporal_smoothing']

    if bin_spikes is None:
        bin_spikes = session_info.get_binned_spikes()

    # define filter.
    filter_len = np.round(temporal_smoothing / time_step).astype(int)
    filt_coeff = signal.windows.hann(filter_len)  # banishing filter
    filt_coeff /= filt_coeff.sum()  # normalize to conserve signal energy

    n_units, n_timebins = bin_spikes.shape
    fr = np.zeros((n_units, n_timebins))
    for unit in np.arange(n_units):
        fr[unit] = signal.filtfilt(filt_coeff, 1, bin_spikes[unit] / time_step)

    return fr


def get_waveform_info(spikes, waveforms, n_samps, samp_rate):
    """
    :param np.array int spikes:
    :param np.ndarray float16 waveforms:
    :param int n_samps:
    :param int samp_rate:
    :return dict wfi: waveform information dictionary
    """
    waveforms = waveforms.astype(np.float32)
    n_spk = len(spikes)
    wfi = {'mean': np.nanmean(waveforms, axis=0),
           'std': np.nanstd(waveforms, axis=0),
           'sem': stats.sem(waveforms, axis=0),
           'nSp': n_spk,
           't_stat': stats.ttest_1samp(waveforms, 0, axis=0)[0],
           'm_fr': n_spk / n_samps * samp_rate}

    # isi in ms
    isi = np.diff(spikes) / samp_rate * 1000
    wfi['isi_h'] = np.histogram(isi, bins=np.linspace(-1, 20, 25))
    wfi['cv'] = np.std(isi) / np.mean(isi)
    return wfi


def get_wf_samps(spikes):
    """
    Returns a matrix of samples centered on each spike for creating waveform plots
    :param spikes: spikes 1d np.array of integers indicating indices of spikes
    :return: np.ndarray n_spikes x 64 of integers
    """

    a = np.zeros((len(spikes), 64), dtype=np.int)
    cnt = 0
    for s in spikes:
        a[cnt] = s + np.arange(64) - 32
        cnt += 1
    return a


def get_waveforms(spikes, data):
    """
    Returns waveforms for each spikes and for each channel [can be a big array]
    :param np.array int spikes:
    :param np.ndarray float16 data: size n_channels x n_samps
    :returns: np.ndarray float16 n_spikes x 64 x n_chans
    """
    wf_samps = get_wf_samps(spikes)
    return np.moveaxis(data[:, wf_samps], 0, -1)


def get_wf_outliers(waveforms, thr=None):
    ###### NOT WORKING #####
    # waveforms = nSpikes x 64 x 4 np.array
    nF = 64 * 4
    nSp = waveforms.shape[0]
    X = np.reshape(waveforms, (nSp, nF))

    Xm = np.mean(X, 0)
    Y = np.zeros(nSp)
    for s in np.arange(nSp):
        Y[s] = spatial.distance.braycurtis(Xm, X[s])
    badSpikes = Y > thr
    # pca = PCA(n_components=2)
    # pca.fit(X)
    # lls = pca.score_samples(X)
    # badSpikes = np.abs(robust_zscore(lls))>thr
    return None


def get_bin_spikes(cluster_spikes, time_resamp, time_orig, time_step=0.02):
    """
    :param np.ndarray object cluster_spikes: array of spike trains
    :param np.array float time_resamp: resampled time vector
    :param np.array float time_orig: original time vector
    :param float time_step: resampling time step
    :return: np.ndarray [n_clusters x n_samps]
    """

    n_samps_orig = len(time_orig)
    n_resamps = len(time_resamp)
    n_clusters = len(cluster_spikes)
    bin_spk = np.zeros((n_clusters, n_resamps), dtype=np.float32)

    for cl in range(n_clusters):
        try:
            spk = cluster_spikes[cl]
            out_of_record_spikes = spk >= n_samps_orig
            if np.any(out_of_record_spikes):
                spk = np.delete(spk, np.where(out_of_record_spikes)[0])

            bin_spk[cl], _ = np.histogram(time_orig[spk], np.concatenate([time_resamp, [time_resamp[-1] + time_step]]))
        except:
            print("Error processing Cluster {}".format(cl))
            pass

    return bin_spk


def smooth_bin_spikes(bin_spikes, time_step, temporal_smoothing=0.125):
    """
    smooth binned spikes and obtains firing rate
    :param np.array ints bin_spikes:
    :param float time_step:
    :param float temporal_smoothing:
    :return: smoothed firing rate, same dimensions as bin_spikes
    """
    filter_len = np.round(temporal_smoothing / time_step).astype(int)
    filt_coeff = signal.windows.hann(filter_len)
    filt_coeff /= filt_coeff.sum()
    return signal.filtfilt(filt_coeff, 1, bin_spikes / time_step).astype(np.float32)


def aggregate_spikes_numpy(cell_spikes, cell_tt_cl, mua_spikes, mua_tt_cl, wfi):
    """
    Wrapper function for get_spikes_numpy
    Deals with Cell and Mua subcategories
    :param cell_spikes: numpy output of get_spikes_numpy
    :param cell_tt_cl: dict output of get_spikes_numpy
    :param mua_spikes: numpy output of get_spikes_numpy
    :param mua_tt_cl: dict output of get_spikes_numpy
    :param wfi: dict of waveform information
    :returns: spikes. object array containing both cell and mua spikes
    :returns: tt_cl.  dict containing the indices and identification info for each cluster
    :returns: wfi2. dict of waveform info with cluster# as keys
    """
    spikes = np.concatenate((cell_spikes, mua_spikes))
    n_cell = len(cell_spikes)
    n_mua = len(mua_spikes)
    tt_cl = {}
    wfi2 = {}
    for unit in range(n_cell):
        tt_cl[unit] = ('cell',) + cell_tt_cl[unit]
        wfi2[unit] = wfi['Cell'][unit]
        wfi2[unit]['unit_type'] = 'cell'
    for unit in range(n_mua):
        tt_cl[unit + n_cell] = ('mua',) + mua_tt_cl[unit]
        wfi2[unit + n_cell] = wfi['Mua'][unit]
        wfi2[unit + n_cell]['unit_type'] = 'mua'

    return spikes, tt_cl, wfi2


def get_spikes_numpy(spikes_dict):
    """
    :param spikes_dict: dictionary of spikes
        contains n_units and tetrodes, each tetrode is a dict of clusters
    :return:
        spikes: a numpy object array of length n_units, each element is a spike train
        tt_cl: a dict with cluster number in the spikes array as keys and tt,cl as values
    """
    n_units = spikes_dict['n_units']
    spikes2 = np.empty(n_units, dtype=object)
    tt_cl = {}
    cnt = 0
    for tt in spikes_dict.keys():
        if tt == 'n_units':
            continue
        for cl, spks in spikes_dict[tt].items():
            spikes2[cnt] = np.array(spks).astype(np.int32)
            tt_cl[cnt] = tt, cl
            cnt += 1

    return spikes2, tt_cl


# private
def _get_tt_spikes(tt, unit_ids, tt_dat, spk_times, cluster_spks, params, spikes, wfi):
    """
    Returns spikes and waveform information for the clusters in the tetrode.
    :param int tt:
    :param list unit_ids:
    :param np.array float16 tt_dat: n_chans x n_samps
    :param np.array ints spk_times: ordered spikes for all clusters
    :param np.array ints cluster_spks: cluster id of each spk in spk_times
    :param dict params:
    :param dict spikes: dictionary of spikes by tetrode and cluster
    :param dict wfi: waveform info by tetrode
    :return: dict spikes
    :return: dict wfi
    """
    spike_buffer = params['spk_recording_buffer']
    samp_rate = params['samp_rate']

    spk_buffer_int = int(spike_buffer * samp_rate)
    cnt = spikes['n_units']
    spikes[str(tt)] = {}
    for cl_id in unit_ids:
        n_samps = tt_dat.shape[1]

        allspikes = spk_times[cluster_spks == cl_id].flatten()
        spikes2 = np.array(allspikes)

        # delete spikes in at beginning and end of recording.
        unit_ids = (spikes2 + spk_buffer_int) < n_samps
        spikes2 = spikes2[unit_ids]
        unit_ids = (spikes2 - spk_buffer_int) > 0
        spikes2 = spikes2[unit_ids]
        spikes2 = spikes2.astype(np.int)

        wf = get_waveforms(spikes2, tt_dat)

        wfi[cnt] = get_waveform_info(spikes2, wf, int(n_samps - 2 * spk_buffer_int), samp_rate)
        wfi[cnt]['tt'] = tt
        wfi[cnt]['cl'] = cl_id

        spikes[str(tt)][str(cl_id)] = spikes2.tolist()
        cnt += 1

    spikes['n_units'] = cnt
    return spikes, wfi



