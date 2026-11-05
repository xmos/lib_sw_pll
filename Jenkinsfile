// This file relates to internal XMOS infrastructure and should be ignored by external users

@Library('xmos_jenkins_shared_library@v0.56.0') _

getApproval()

// Each parallel branch runs on its own agent, so each needs its own checkout.
def checkoutRepo() {
    println "Stage running on ${env.NODE_NAME}"
    def (server, user, repo) = extractFromScmUrl()
    env.REPO_NAME = repo
    dir(repo) {
        checkoutScmShallow()
    }
}

pipeline {

    agent none

    parameters {
        string(
            name: 'TOOLS_VERSION_XS',
            defaultValue: '15.3.1',
            description: 'The xcore.ai (XS) XTC tools version'
        )
        string(
            name: 'XMOSDOC_VERSION',
            defaultValue: 'v8.1.2',
            description: 'The xmosdoc version'
        )
        string(
            name: 'TOOLS_VERSION_VX',
            defaultValue: 'bob@develop',
            description: 'The XCORE-400 (VX) tools version (Bob)'
        )
        string(
            name: 'TOOLS_VERSION_VX_XCC',
            defaultValue: 'slipgate@master:143',
            description: 'The XCORE-400 (VX) XTC tools version (slipgate)'
        )
        string(
            name: 'INFR_APPS_VERSION',
            defaultValue: 'v3.6.0',
            description: 'The infr_apps version'
        )
    }

    options {
        buildDiscarder(xmosDiscardBuildSettings(onlyArtifacts = false))
        skipDefaultCheckout()
        timestamps()
    }

    stages {
        stage('🏗️ Build and tests') {
            // Each branch has its own agent and checkout so venvs, build dirs and tests/bin never collide.
            parallel {
                stage('XS') {
                    agent {
                        label 'linux && 64 && documentation'
                    }
                    stages {
                        stage('Checkout XS') {
                            steps {
                                checkoutRepo()
                            }
                        }

                        stage('Build XS examples') {
                            steps {
                                script {
                                    withTools(params.TOOLS_VERSION_XS) {
                                        // The top-level examples project also includes the VX-only MASH app.
                                        ['app_fixed_clock', 'app_i2s_slave_lut', 'app_simple_lut', 'app_simple_sdm'].each { app ->
                                            dir("${REPO_NAME}/examples/${app}") {
                                                xcoreBuild(buildDir: 'build-xs')
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        stage('Test XS') {
                            steps {
                                dir("${REPO_NAME}/tests") {
                                    createVenv(reqFile: "requirements.txt")
                                    withVenv {
                                        withTools(params.TOOLS_VERSION_XS) {
                                            xcoreBuild(buildDir: 'build-xs', archiveBins: false)
                                            sh "pytest -n auto --dist=loadgroup --junitxml=results.xml -rA -v --durations=0 -o junit_logging=all"
                                        }
                                        zip archive: true, zipFile: "tests.zip", dir: "bin"
                                        archiveArtifacts artifacts: "bin/**/timing-report*.txt", allowEmptyArchive: false
                                    }
                                }
                            }
                            post {
                                always {
                                    junit "${REPO_NAME}/tests/results.xml"
                                }
                            }
                        }

                    }
                    post {
                        cleanup {
                            xcoreCleanSandbox()
                        }
                    }
                }

                stage('Python examples') {
                    agent {
                        label 'linux && 64 && documentation'
                    }
                    stages {
                        stage('Checkout Python examples') {
                            steps {
                                checkoutRepo()
                            }
                        }

                        stage('Run Python examples') {
                            steps {
                                dir("${REPO_NAME}/python") {
                                    createVenv(reqFile: "requirements.txt")
                                    withVenv {
                                        dir("sw_pll") {
                                            sh 'python sw_pll_sim.py LUT && python sw_pll_sim.py SDM && python sw_pll_sim.py MASH'
                                        }
                                    }
                                    archiveArtifacts artifacts: "sw_pll/*.png,python/sw_pll/*.wav", allowEmptyArchive: false
                                }
                            }
                        }
                    }
                    post {
                        cleanup {
                            xcoreCleanSandbox()
                        }
                    }
                }

                stage('VX') {
                    agent {
                        label 'linux && 64 && documentation'
                    }
                    stages {
                        stage('Checkout VX') {
                            steps {
                                checkoutRepo()
                            }
                        }

                        stage('Build VX examples') {
                            steps {
                                withTools(params.TOOLS_VERSION_VX_XCC) {
                                    dir("${REPO_NAME}/examples/app_simple_mash") {
                                        xcoreBuild(buildDir: 'build-vx')
                                    }
                                }
                            }
                        }

                        stage('Build Bob API smoke app') {
                            steps {
                                withTools(params.TOOLS_VERSION_VX) {
                                    dir("${REPO_NAME}/tests/test_sw_pll_api_smoke") {
                                        xcoreBuild()
                                    }
                                }
                            }
                        }

                        stage('Test VX MASH') {
                            steps {
                                dir("${REPO_NAME}/tests") {
                                    createVenv(reqFile: "requirements.txt")
                                    withVenv {
                                        withTools(params.TOOLS_VERSION_VX_XCC) {
                                            dir("test_mash") {
                                                xcoreBuild(buildDir: 'build-vx', archiveBins: false)
                                            }
                                            // xsim models mean PLL frequency only, not the MASH sequence.
                                            sh "pytest -n auto --dist=loadgroup --run-mash -m mash_xsim test_lib_sw_pll.py test_lib_sw_pll_equiv.py --junitxml=results-mash.xml -rA -v --durations=0 -o junit_logging=all"
                                        }
                                        archiveArtifacts artifacts: "bin/**/mash-*.csv,bin/**/mash-*.png", allowEmptyArchive: false
                                    }
                                }
                            }
                            post {
                                always {
                                    junit "${REPO_NAME}/tests/results-mash.xml"
                                }
                            }
                        }
                    }
                    post {
                        cleanup {
                            xcoreCleanSandbox()
                        }
                    }
                }

                stage('Checks and docs') {
                    agent {
                        label 'linux && 64 && documentation'
                    }
                    stages {
                        stage('Checkout checks') {
                            steps {
                                checkoutRepo()
                            }
                        }

                        stage('Repo checks') {
                            steps {
                                warnError("Repo checks failed") {
                                    runRepoChecks("${WORKSPACE}/${REPO_NAME}")
                                }
                            }
                        }

                        stage('Doc build') {
                            steps {
                                dir(REPO_NAME) {
                                    buildDocs()
                                }
                            }
                        }

                        stage("Archive sandbox") {
                            steps {
                                archiveSandbox(REPO_NAME)
                            }
                        }
                    }
                    post {
                        cleanup {
                            xcoreCleanSandbox()
                        }
                    }
                }
            }
        } // stage('🏗️ Build and tests')

        stage('🚀 Release') {
            when {
                expression { triggerRelease.isReleasable() }
            }
            steps {
                triggerRelease()
            }
        } // stage "Release"
    }
}
