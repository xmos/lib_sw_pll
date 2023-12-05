@Library('xmos_jenkins_shared_library@v0.23.0') _


getApproval()


pipeline {
    agent none

    options {
        disableConcurrentBuilds()
        skipDefaultCheckout()
        timestamps()
        // on develop discard builds after a certain number else keep forever
        buildDiscarder(logRotator(
            numToKeepStr:         env.BRANCH_NAME ==~ /develop/ ? '25' : '',
            artifactNumToKeepStr: env.BRANCH_NAME ==~ /develop/ ? '25' : ''
        ))
    }
    parameters {
        string(
            name: 'TOOLS_VERSION',
            defaultValue: '15.2.1',
            description: 'The XTC tools version'
        )
    }
    environment {
        REPO = 'lib_sw_pll'
        PYTHON_VERSION = "3.10.5"
        VENV_DIRNAME = ".venv"
    }

    stages {
        stage('Build and tests') {
            agent {
                label 'linux&&64'
            }
            stages{
                stage('Checkout'){
                    steps {
                        sh 'mkdir ${REPO}'
                        // source checks require the directory
                        // name to be the same as the repo name
                        dir("${REPO}") {
                            // checkout repo
                            checkout scm
                            installPipfile(false)
                            withVenv {
                                withTools(params.TOOLS_VERSION) {
                                    sh './tools/ci/checkout-submodules.sh'
                                }
                            }
                        }
                    }
                }
                stage('Docs') {
                    environment { XMOSDOC_VERSION = "v4.0" }
                    steps {
                        dir("${REPO}") {
                            sh "docker pull ghcr.io/xmos/xmosdoc:$XMOSDOC_VERSION"
                            sh """docker run -u "\$(id -u):\$(id -g)" \
                                --rm \
                                -v \$(pwd):/build \
                                ghcr.io/xmos/xmosdoc:$XMOSDOC_VERSION -v html latex"""

                            // Zip and archive doc files
                            zip dir: "doc/_build/", zipFile: "sw_pll_docs.zip"
                            archiveArtifacts artifacts: "sw_pll_docs.zip"
                        }
                    }
                }
                stage('Build'){
                    steps {
                        dir("${REPO}") {
                            withVenv {
                                withTools(params.TOOLS_VERSION) {
                                    sh './tools/ci/do-ci-build.sh'
                                }
                            }
                        }
                    }
                }
                stage('Test'){
                    steps {
                        dir("${REPO}") {
                            withVenv {
                                withTools(params.TOOLS_VERSION) {
                                    catchError {
                                        sh './tools/ci/do-ci-tests.sh'
                                    }
                                    zip archive: true, zipFile: "build.zip", dir: "build"
                                    zip archive: true, zipFile: "tests.zip", dir: "tests/bin"
                                    archiveArtifacts artifacts: "tests/bin/timing-report*.txt", allowEmptyArchive: false

                                    junit 'tests/results.xml'
                                }
                            }
                        }
                    }
                }
                stage('Python examples'){
                    steps {
                        dir("${REPO}") {
                            withVenv {
                                catchError {
                                    sh './tools/ci/do-model-examples.sh'
                                }
                                archiveArtifacts artifacts: "python/sw_pll/*.png,python/sw_pll/*.wav", allowEmptyArchive: false
                            }
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
    }
}
